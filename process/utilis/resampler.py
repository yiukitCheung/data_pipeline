import pandas as pd
import logging
import traceback
from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import (
    col, max as spark_max, min as spark_min, first, last, 
        sum as spark_sum, lit, to_date, row_number, when, expr, create_map, explode, array, count
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
from prefect import get_run_logger
import pytz
import pandas_market_calendars as mcal
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.utils import DateTimeTools

load_dotenv()

# Standard logging configuration for standalone execution
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
        
        # Try to get Prefect logger, fall back to standard logger if not in Prefect context
        try:
            self.logger = get_run_logger()
        except Exception:
            self.logger = logging.getLogger(__name__)
        
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
            self.logger.error(f"Error getting trading days: {e}")
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
            self.logger.warning("No trading days found, using all days")
            return df
        
        trading_days_df = trading_days_df.withColumnRenamed("date", "trading_date")
        filtered_df = df.join(
            trading_days_df,
            to_date(df.date) == to_date(col("trading_date")),
            "inner"
        ).drop("trading_date")
        
        self.logger.info(f"Filtered to {filtered_df.count()} trading days across all symbols")
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
    
    def _update_in_progress(self, orginal_resampled_df, latest_raw_df, interval):
        """Update the in_progress candles: modify close if still in progress, or mark complete if interval finished
        
        Args:
            orginal_raw_df: Input DataFrame with newly resampled OHLCV
            latest_raw_df: DataFrame with cutoff meta containing latest candle_id and date for in-progress
        """
        self.logger.info(f"Resampler: Updating in-progress candles for interval: {interval}")
        # Filter only in progress candles
        df = orginal_resampled_df.filter(col("status") == "in_progress")
        if df.count() == 0:
            self.logger.info(f"Processing interval: {interval} - No in-progress candles found, skipping to next interval")
            
            df = df.withColumnRenamed("latest_candle_id", "candle_id")
            df = df.drop("latest_date")
            # Reorder the columns 
            df = df.select("symbol", "interval", "candle_id", "date", "open", "high", "low", "close", "volume", "type", "status")
            return df
            
        # Define a UDF to compute days left to complete a candle
        def get_days_left_to_complete_candle(latest_candle_date: str, interval: str):
            """
            Get the number of days left to complete a candle.
            Used in: resampler.py
            """
            try:
                # Get NYSE calendar
                nyse = mcal.get_calendar('NYSE')
                
                # Get current NY time
                ny_tz = pytz.timezone('America/New_York')
                today = datetime.now(ny_tz).strftime('%Y-%m-%d')
                
                # Convert latest_candle_date to datetime - handle time component
                # Check if time component exists and use appropriate format
                if ' ' in latest_candle_date:
                    # Format with time component
                    latest_candle_date = datetime.strptime(latest_candle_date, '%Y-%m-%d %H:%M:%S')
                else:
                    # Format without time component
                    latest_candle_date = datetime.strptime(latest_candle_date, '%Y-%m-%d')
                
                # Get market schedule
                schedule = nyse.schedule(start_date=latest_candle_date, end_date=today)
                if schedule.empty:
                    return 0  # Return 0 if market is closed today
                
                # Get the days left to complete the candle
                days_left = int(interval) - len(schedule)
            
                return max(0, days_left)  # Ensure we don't return negative values
            except Exception as e:
                # We can't use self.logger here since this runs on workers
                print(f"Error in get_days_left_to_complete_candle: {e}")
                return 0  # Default to 0 on error
        
        days_left_udf = udf(get_days_left_to_complete_candle, IntegerType())
        
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
        ).sort("symbol", "date")
        
        # Crearte Rownumber for each symbol 
        window_spec = Window.partitionBy("symbol").orderBy("date")
        df = df.withColumn("row_num", row_number().over(window_spec))
        df = df.filter(col("row_num") == 1)
        df = df.drop("row_num")

        self.logger.info(f"Processing interval: {interval} - Updated {df.count()} in-progress candles")
        return df
    
    def _add_completed(self, original_resampled_df, latest_raw_df, interval):
        """Add a new candle to the DataFrame for completed candles
    
        Args:
            original_resampled_df: Input DataFrame with resampled data
            latest_raw_df: DataFrame with latest raw data for each symbol
        """
        self.logger.info(f"Resampler: Adding completed candles for interval: {interval}")
        # Filter only complete candles
        df = original_resampled_df.filter(col("status") == "complete")
        
        if df.count() == 0:
            self.logger.info(f"Processing interval: {interval} - No complete candles found, skipping to next interval")
            df = df.withColumnRenamed("latest_candle_id", "candle_id")
            df = df.drop("latest_date")
            
            # Reorder the columns 
            df = df.select("symbol", "interval", "candle_id", "date", "open", "high", "low", "close", "volume", "type", "status")
            
            return df
        
        # Get unique symbol and interval combinations from complete candles
        symbol_intervals = df.select("symbol", "interval", "latest_candle_id").distinct()
        
        # Join with latest_raw_df to get latest data for each symbol
        new_candles = symbol_intervals.alias("original_resampled").join(
            latest_raw_df.alias("latest_raw"),
            on=["symbol"],
            how="left"
        )
        
        # Create new candle entries using the latest raw data
        new_candles = new_candles.select(
            col("latest_raw.symbol"),
            col("original_resampled.interval"),
            (col("original_resampled.latest_candle_id") + 1).alias("candle_id"),
            col("latest_raw.date").alias("date"),
            col("latest_raw.open").alias("open"),  # Use latest raw open
            col("latest_raw.high").alias("high"),  # Use latest raw high
            col("latest_raw.low").alias("low"),    # Use latest raw low
            col("latest_raw.close").alias("close"), # Use latest raw close
            col("latest_raw.volume").alias("volume"), # Use latest raw volume 
            lit("cs").alias("type"),     # Type is always "cs"
            when(col("original_resampled.interval") == 1, lit("complete"))
                .otherwise(lit("in_progress")).alias("status")  # Complete for interval=1, in_progress for others
        )
        self.logger.info(f"Processing interval: {interval} - Added {new_candles.count()} completed candles")
        return new_candles
    
    def _process(self, df, interval, mode, latest_trading_date = None, metadata_df=None):
        """Process a single interval
        
        Args:
            df: Input DataFrame
            interval: Resampling interval
            latest_trading_date: Latest trading date
            
        Returns:
            Resampled DataFrame for the interval
        """
        self.logger.info(f"Processing interval: {interval}")    
        
        # ===============================
        # production mode
        # ===============================
        if mode == "production":
            # Filter to only the interval we want to fill the gap
            df = df.filter(col("interval") == interval)
            
            # Update the in_progress 
            in_progress_df = self._update_in_progress(df, metadata_df, interval)
            in_progress_df.show(10)
            # Add a new candle if complete
            completed_df = self._add_completed(df, metadata_df, interval)
            completed_df.show(10)
            # Combine the in_progress and completed candles
            df = in_progress_df.unionAll(completed_df)
            
            # Write to parquet
            df.write.mode("overwrite").parquet(f"data/resampled/interval_{interval}.parquet")

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
                self.logger.warning("Resampler: Empty DataFrame provided")
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
                    self.logger.warning("Resampler: No data left after filtering")
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
            exit()          
            return resampled_df
            
        except Exception as e:
            self.logger.error(f"Resampler: Error in bulk processing: {e}")
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
