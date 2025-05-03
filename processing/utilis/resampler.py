import pandas as pd
import logging
import traceback
from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import (
    col, max as spark_max, min as spark_min, first, last, 
    sum as spark_sum, lit, to_date, row_number, when, expr, create_map, explode, array
)
from pyspark.sql.functions import udf
from pyspark.sql.types import IntegerType
from itertools import chain
import pandas_market_calendars as mcal
from functools import reduce
from tools import postgres_client
from dotenv import load_dotenv
import os
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.utilis import DateTimeTools

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ResampleProcessor:
    
    def __init__(self, spark, intervals: list, mode: str):
        """Initialize ResampleProcessor with Spark session and intervals
        
        Args:
            spark: SparkSession instance
            intervals: List of intervals in days [1,3,5,8,13] etc.
        """
        self.spark = spark
        self.intervals = intervals
        self.postgres_tool = postgres_client.PostgresTools(os.getenv('POSTGRES_URL'))
        self.mode = mode
        
    def _get_trading_days(self, start_date, end_date):
        """Get NYSE trading days for the given date range
        
        Args:
            start_date: Start date for trading calendar
            end_date: End date for trading calendar
            
        Returns:
            Spark DataFrame with trading dates
        """
        try:
            nyse = mcal.get_calendar('NYSE')
            schedule = nyse.schedule(start_date=start_date, end_date=end_date)
            trading_dates = pd.DataFrame({
                'date': pd.DatetimeIndex(schedule['market_close'])
                .tz_convert('UTC')
                .normalize()
            })
            return self.spark.createDataFrame(trading_dates)
        except Exception as e:
            logging.error(f"Error getting trading days: {e}")
            traceback.print_exc()
            return self.spark.createDataFrame(pd.DataFrame({'date': []}))
        
    def _filter_trading_days(self, df, trading_days_df):
        """Filter data to include only trading days
        
        Args:
            df: Input Spark DataFrame
            trading_days_df: DataFrame with trading days
            
        Returns:
            Filtered Spark DataFrame
        """
        if trading_days_df.count() == 0:
            logging.warning("No trading days found, using all days")
            return df
        
        trading_days_df = trading_days_df.withColumnRenamed("date", "trading_date")
        filtered_df = df.join(
            trading_days_df,
            to_date(df.date) == to_date(col("trading_date")),
            "inner"
        ).drop("trading_date")
        
        logging.info(f"Filtered to {filtered_df.count()} trading days across all symbols")
        return filtered_df
    
    def _create_candle_groups(self, df, interval, candle_offsets=None):
        """Create candle groups for resampling
        
        Args:
            df: Input Spark DataFrame
            interval: Resampling interval in days
            candle_offsets: Optional dictionary of {symbol: last_candle_id} for catch-up mode
            
        Returns:
            DataFrame with candle grouping information
        """
        window_spec = Window.partitionBy("symbol").orderBy("date")
        df = df.withColumn("row_num", row_number().over(window_spec)).sort("date")
        
        if candle_offsets:
            mapping_expr = create_map([lit(x) for x in chain(*candle_offsets.items())])
            df = df.withColumn("candle_offset", mapping_expr.getItem(col("symbol")))
            df = df.withColumn(
                "candle_id",
                ((col("row_num") - lit(1)) / lit(interval)).cast("int") + col("candle_offset").cast("int")
            )
            
        else:
            df = df.withColumn(
                "candle_id",
                ((col("row_num") - lit(1)) / lit(interval)).cast("int")
            )
        
        window_first_date = Window.partitionBy("symbol", "candle_id").orderBy("date")
        return df.withColumn("group_date", first("date").over(window_first_date))
    
    def _aggregate_candles(self, df):
        """Aggregate OHLCV data for each candle group
        
        Args:
            df: Input DataFrame with candle groups
            
        Returns:
            Aggregated DataFrame with OHLCV data
        """
        return df.groupBy("symbol", "candle_id", "group_date").agg(
            first("open").alias("open"),
            spark_max("high").alias("high"),
            spark_min("low").alias("low"),
            last("close").alias("close"),
            spark_sum("volume").alias("volume")
        )
        
    def _add_metadata(self, df, interval, latest_trading_date):
        """Add metadata columns to DataFrame
        
        Args:
            df: Input DataFrame
            interval: Resampling interval
            latest_trading_date: Latest trading date
            
        Returns:
            DataFrame with metadata columns
        """
        latest_trading_date = list(self.postgres_tool.fetch_latest_date('raw').values())[0] if self.mode == 'catch_up' else latest_trading_date
        
        return df \
            .withColumnRenamed("group_date", "date") \
            .withColumn("interval", lit(interval)) \
            .withColumn("type", lit("cs")) \
            .withColumn(
                "status",
                when(
                    col("date") + expr(f"INTERVAL {interval - 1} DAYS") <= lit(latest_trading_date),
                    lit("complete")
                ).otherwise(lit("in_progress"))
            )
    
    def _update_in_progress(self, orginal_raw_df, latest_raw_df):
        """Update the in_progress candles: modify close if still in progress, or mark complete if interval finished
        
        Args:
            orginal_raw_df: Input DataFrame with newly resampled OHLCV
            latest_raw_df: DataFrame with cutoff meta containing latest candle_id and date for in-progress
        """
        # Get the latest date from the metadata
        latest_date = latest_raw_df.agg(spark_max("date")).collect()[0][0]
        
        # Filter only in progress candles
        df = orginal_raw_df.filter(col("status") == "in_progress")
        if df.count() == 0:
            logging.info(f"No in-progress candles found, skipping to next interval")
            return df
            
        # Define a UDF to compute days left to complete a candle
        def days_left_to_complete(latest_date_str, interval):
            try:
                # Convert the date string to datetime and extract just the date part
                latest_date = pd.to_datetime(latest_date_str).date()
                return DateTimeTools.get_days_left_to_complete_candle(str(latest_date), str(interval))
            except Exception as e:
                logging.error(f"Failed to calculate days_left_to_complete: {e}")
                return 0

        days_left_udf = udf(days_left_to_complete, IntegerType())
        
        # Join to bring in the latest candle metadata (date, candle_id, interval)
        df = df.alias("df").join(
            latest_raw_df.alias("meta"),
            on=["symbol"],
            how="left"
        )
        
        # Drop the null close values
        df = df.filter(col("df.close").isNotNull())
        
        # Add column to compute days left 
        df = df.withColumn(
            "days_left",
            days_left_udf(col("df.date").cast("string"), col("interval").cast("string"))
        )
        
        # Update status based on days left
        df = df.withColumn(
            "status",
            when(col("days_left") <= 0, lit("complete")).otherwise(lit("in_progress"))
        )
        
        # Create the final DataFrame
        # 1. Keep original symbol, interval, candle_id, date
        # 2. Maintain original open, high, low values
        # 3. Update close price and status
        df = df.select(
            col("df.symbol").alias("symbol"),
            col("interval"),
            col("latest_candle_id").alias("candle_id"),
            col("df.date").alias("date"),  # Keep original date
            col("df.open").alias("open"),  # Keep original open
            col("df.high").alias("high"),  # Keep original high
            col("df.low").alias("low"),    # Keep original low
            col("meta.close").alias("close"),  # Keep original close
            col("df.volume").alias("volume"),  # Keep original volume
            col("df.type").alias("type"),  # Keep original type
            col("status")  # Updated status based on days_left
        )
        
        # Only filter the latest date
        df = df.filter(col("date") == lit(latest_date))
        df.show(20)
        exit()
        
        return df
    
    # def _add_new_candle(self, df, metadata_df):
    #     """Add a new candle to the DataFrame
    
    #     Args:
    #         df: Input DataFrame
    #         metadata_df: DataFrame with cutoff meta containing latest candle_id and date for in-progress
    #     """
    #     # Filter only in progress candles
    #     df = df.filter(col("status") == "complete")
    #     if df.count() == 0:
    #         logging.info(f"No complete candles found, skipping to next interval")
    #         return df
    
    #     # Get the latest candle_id and date
    #     latest_candle_id = metadata_df.agg(spark_max("candle_id")).collect()[0][0]
    #     latest_date = metadata_df.agg(spark_max("date")).collect()[0][0]
    
    #     # Add a new candle
    
    
    def _process(self, df, interval, mode, latest_trading_date = None, metadata_df=None):
        """Process a single interval
        
        Args:
            df: Input DataFrame
            interval: Resampling interval
            latest_trading_date: Latest trading date
            
        Returns:
            Resampled DataFrame for the interval
        """
        logging.info(f"Processing interval: {interval}")
        
        # ===============================
        # production mode
        # ===============================
        if mode == "production":
            # Filter to only the interval we want to fill the gap
            df = df.filter(col("interval") == interval)
            # Update the in_progress 
            df = self._update_in_progress(df, metadata_df)
            
            # Add a new candle if complete
            # df = self._add_new_candle(df, metadata_df)
            
            return df
        # ===============================
        # Reset mode
        # ===============================
        elif mode == "reset":
            grouped_df = self._create_candle_groups(df, interval)
            
            # Step 1. Aggregate candles
            aggregated_df = self._aggregate_candles(grouped_df)
            
            # Step 2. Add metadata
            aggregated_df = self._add_metadata(aggregated_df, interval, latest_trading_date)
            
            # Step 3. Filter to only the data beyond the latest_trading_date
            filtered_df = aggregated_df.filter(col("date") > lit(latest_trading_date)) if mode == "catch_up" else aggregated_df
            
            return filtered_df
            
    def apply(self, df, metadata_df=None, mode="production"):
        """Resample time series data for all symbols and intervals

        Args:
            df: Spark DataFrame with OHLCV data
            metadata_df: Spark DataFrame with metadata
            mode: either "reset" or "catch_up"
            
        Returns:
            Resampled Spark DataFrame
        """
        try:
            if df.count() == 0:
                logging.warning("Resampler: Empty DataFrame provided")
                return self.spark.createDataFrame([])
            
            # ===============================
            # Reset mode
            # ===============================
            if mode == "reset":
                # Get date range
                date_range = df.select(
                    spark_min("date").alias("min_date"), 
                    spark_max("date").alias("max_date")
                ).collect()[0]
            
                # Get the trading days for the date range
                trading_days_df = self._get_trading_days(
                    date_range["min_date"], 
                    date_range["max_date"]
                )
                # Filter the data to only include trading days
                df = self._filter_trading_days(df, trading_days_df)
                
                # Get latest trading date for status calculation
                latest_trading_date = df.agg(spark_max("date")).collect()[0][0]
            
                # Check if there is any data left after filtering
                if df.count() == 0:
                    logging.warning("Resampler: No data left after filtering")
                    return self.spark.createDataFrame([])
            # Process data by interval
            resampled_dfs = []
            for interval in self.intervals:
                interval_df = self._process(
                    df, 
                    interval,  
                    mode,
                    latest_trading_date=latest_trading_date if mode == 'reset' else None,
                    metadata_df=metadata_df
                )
                
                resampled_dfs.append(interval_df)
                
            # Combine results cumulatively
            resampled_df = reduce(lambda df1, df2: df1.unionAll(df2), resampled_dfs)            
            return resampled_df
            
        except Exception as e:
            logging.error(f"Resampler: Error in bulk processing: {e}")
            traceback.print_exc()
            return self.spark.createDataFrame([])

# Testing    
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    postgres_tool = postgres_client.PostgresTools(os.getenv('POSTGRES_URL'))
    symbol_data = postgres_tool.fetch_symbol_data("raw", "AAPL")
    if symbol_data.empty:
        logging.error("Resampler: No data found for AAPL")
        exit(1)
        
    # Initialize Spark session
    spark = SparkSession.builder \
        .appName("ResampleProcessor") \
        .config("spark.driver.host", "localhost") \
        .getOrCreate()
    
    try:
        # Create resampler instance
        resampler = ResampleProcessor(spark, [1, 3, 5, 8, 13])
        
        # Test trading days retrieval
        start_date = symbol_data['date'].min()
        end_date = symbol_data['date'].max()
        trading_days = resampler._get_trading_days(start_date, end_date)
        
        # Display results
        print(f"Trading days between {start_date.date()} and {end_date.date()}:")
        
        # Process the data
        resampled_df = resampler.apply_bulk(symbol_data)
        print("\nResampled data:")

    except Exception as e:
        logging.error(f"Error in main execution: {e}")
        traceback.print_exc()
    finally:
        spark.stop()
