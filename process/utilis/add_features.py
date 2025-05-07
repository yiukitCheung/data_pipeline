import logging
import time
import pandas as pd
from pyspark.sql import Window
from pyspark.sql.functions import col, pandas_udf, PandasUDFType
from pyspark.sql.types import StructType, StructField, DoubleType, StringType, TimestampType, IntegerType
import ta
import traceback
import sys, os
from functools import reduce

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools import postgres_client
from datetime import datetime
from config.load_setting import load_setting
from dotenv import load_dotenv

load_dotenv()


class FeaturesEngineer:
    """
    Feature engineering for financial time series data using Spark
    """
    def __init__(self, mode="reset"):
        """
        Initialize with DataFrame

        Args:
            mode: mode of operation ("reset" or "catch_up")
        """
        self.mode = mode

        # Define schema for the pandas UDF
        # This schema should match the output of the process_group function
        self.output_schema = StructType([
            StructField("date", TimestampType(), True),
            StructField("symbol", StringType(), True),
            StructField("interval", StringType(), True),
            StructField("indicator_id", IntegerType(), True),
            StructField("value", DoubleType(), True)
        ])

    def process_group(self, pandas_df: pd.DataFrame, prev_indicators_broadcast, indicators_config_broadcast, mode) -> pd.DataFrame:
        """
        Process a single group of data for indicators.
        This function is executed on the Spark workers.

        Args:
            pandas_df: A pandas DataFrame containing data for a single group (e.g., one symbol/interval).
            prev_indicators_broadcast: Broadcast variable containing previous indicator data (as a pandas DataFrame).
            indicators_config_broadcast: Broadcast variable containing indicator configuration (as a pandas DataFrame).
            mode: The processing mode ("reset" or "catch_up").

        Returns:
            A pandas DataFrame with calculated indicators in a long format.
        """
        # Ensure the data is sorted by date within each group
        pandas_df = pandas_df.sort_values('date')

        # Access broadcast variables' values
        prev_indicators_df = prev_indicators_broadcast.value if prev_indicators_broadcast else None
        indicators_config = indicators_config_broadcast.value

        # Handle 'catch_up' mode: prepend previous data if available
        if mode == "catch_up" and prev_indicators_df is not None and not prev_indicators_df.empty:
            # Filter previous data for the current symbol/interval
            current_symbol = pandas_df['symbol'].iloc[0]
            current_interval = str(pandas_df['interval'].iloc[0]) # Ensure interval is string for comparison

            prev_df_filtered = prev_indicators_df[
                (prev_indicators_df['symbol'] == current_symbol) &
                (prev_indicators_df['interval'] == current_interval)
            ][['date', 'symbol', 'interval', 'close']] # Select necessary columns

            if not prev_df_filtered.empty:
                # Concatenate previous data and current data
                # Use drop_duplicates to handle potential overlap at the start of the current data
                # Sort again to ensure correct time series order after concatenation
                pandas_df = pd.concat([prev_df_filtered, pandas_df], ignore_index=True)
                pandas_df = pandas_df.drop_duplicates(subset=["date", "symbol", "interval"]).sort_values('date')


        # Extract common values once after potential concatenation
        symbol = pandas_df['symbol'].iloc[0]
        interval = str(pandas_df['interval'].iloc[0])
        dates = pandas_df['date'].values # Use .values for potentially better performance

        # Store all results in a list
        all_results = []

        # Iterate through indicator configurations
        for _, indicator in indicators_config.iterrows():
            try:
                indicator_type = indicator['type'].lower()
                params = indicator['params']
                indicator_id = indicator['indicator_id']

                values = None # Initialize values

                if indicator_type == 'ema':
                    values = ta.trend.ema_indicator(
                        close=pandas_df['close'],
                        window=params['window'],
                        fillna=True # Fill with NaN where indicator cannot be calculated
                    )

                elif indicator_type == 'macd':
                    # MACD returns a Series for the MACD line by default
                    macd_indicator = ta.trend.MACD(
                        close=pandas_df['close'],
                        window_slow=params['long'],
                        window_fast=params['short'],
                        window_sign=params['signal']
                    )
                    values = macd_indicator.macd() # Get the MACD line


                elif indicator_type == 'rsi':
                    values = ta.momentum.rsi(
                        close=pandas_df['close'],
                        window=params['window'],
                        fillna=True # Fill with NaN where indicator cannot be calculated
                    )

                else:
                    # Log unsupported indicator type (this won't show in driver logs directly)
                    # Consider a mechanism to collect errors from workers if needed
                    print(f"Unsupported indicator type in worker: {indicator_type}")
                    continue # Skip to the next indicator

                # If values were calculated, create a result DataFrame
                if values is not None:
                    # Ensure the length of dates and values match after potential concatenation/sorting
                    if len(dates) == len(values):
                        result_df = pd.DataFrame({
                            'date': dates,
                            'symbol': symbol,
                            'interval': interval,
                            'indicator_id': indicator_id,
                            'value': values.values # Use .values for potentially better performance
                        })
                        all_results.append(result_df)
                    else:
                        # Log length mismatch (won't show in driver logs directly)
                        print(f"Length mismatch for {indicator_type}: dates={len(dates)}, values={len(values)}")


            except Exception as e:
                # Log error in worker (won't show in driver logs directly)
                print(f"Error calculating {indicator['type']} in worker for {symbol}/{interval}: {e}")
                # traceback.print_exc() # Uncomment for detailed worker traceback if needed
                continue # Continue with the next indicator


        # Concatenate all results into a single DataFrame for this group
        if all_results:
            # Ensure the concatenated DataFrame has the correct columns and types
            final_group_df = pd.concat(all_results, ignore_index=True)
            # Align columns and types to match the output_schema
            # This helps prevent schema mismatch errors when Spark combines results
            final_group_df = final_group_df[
                ['date', 'symbol', 'interval', 'indicator_id', 'value']
            ].astype({
                'date': 'datetime64[ns]', # Pandas timestamp type
                'symbol': str,
                'interval': str,
                'indicator_id': int,
                'value': float # Pandas float type for DoubleType
            })
            return final_group_df
        else:
            # Return an empty DataFrame with the expected columns if no indicators were calculated
            return pd.DataFrame(columns=['date', 'symbol', 'interval', 'indicator_id', 'value'])

    def apply(self, spark_df, prev_indicators_pd=None, indicators_config_pd=None):
        """
        Apply indicators using applyInPandas for distributed processing.

        Args:
            spark_df: Input Spark DataFrame with financial data.
            prev_indicators_pd: Optional pandas DataFrame with previous indicator data for catch-up.
            indicators_config_pd: pandas DataFrame with indicator configurations.

        Returns:
            Spark DataFrame with calculated indicators in a long format.
        """
        try:
            start_time = time.time()
            logging.info(f"FeaturesEngineer: Starting indicator calculation in mode: {self.mode}")

            # Broadcast necessary dataframes if they are not too large
            # This makes them available to all worker tasks
            prev_indicators_broadcast = None
            if prev_indicators_pd is not None and not prev_indicators_pd.empty:
                # Consider a size check here before broadcasting very large dataframes
                logging.info("FeaturesEngineer: Broadcasting previous indicators data.")
                prev_indicators_broadcast = spark_df.sparkSession.sparkContext.broadcast(prev_indicators_pd)
            else:
                logging.info("FeaturesEngineer: No previous indicators data provided or data is empty.")


            if indicators_config_pd is None or indicators_config_pd.empty:
                logging.error("FeaturesEngineer: Indicator configuration is missing or empty.")
                return spark_df # Or raise an error


            logging.info("FeaturesEngineer: Broadcasting indicator configuration.")
            indicators_config_broadcast = spark_df.sparkSession.sparkContext.broadcast(indicators_config_pd)


            # Check the current number of partitions
            current_partitions = spark_df.rdd.getNumPartitions()
            logging.info(f"FeaturesEngineer: Current number of partitions: {current_partitions}")

            # Count unique symbol/interval combinations
            unique_combinations = spark_df.select("symbol", "interval").distinct().count()
            logging.info(f"FeaturesEngineer: Number of unique symbol/interval combinations: {unique_combinations}")

            # Determine optimal partition count - aim for a balance
            # A common strategy is to have roughly 2-4 tasks per CPU core in the cluster
            # Or base it on the number of unique groups if that's smaller
            num_cores = spark_df.sparkSession.sparkContext.defaultParallelism # Get default parallelism
            target_partitions = min(unique_combinations, max(num_cores * 2, 256)) # Example: min of unique groups or (cores * 2), capped at 128/256 etc.
            # Adjust 128/256 based on cluster size and data volume per group

            processed_df = spark_df
            # Only repartition if the difference is significant
            # Avoid excessive repartitioning which can be costly
            if unique_combinations > 0 and abs(current_partitions - target_partitions) / unique_combinations > 0.1: # Repartition if target is significantly different based on unique groups
                logging.info(f"FeaturesEngineer: Repartitioning from {current_partitions} to {target_partitions} partitions based on 'symbol'.")
                processed_df = spark_df.repartition(target_partitions, "symbol")
            elif unique_combinations == 0:
                logging.warning("FeaturesEngineer: Input DataFrame is empty, skipping repartitioning.")
                # Return an empty DataFrame matching the output schema
                return spark_df.sparkSession.createDataFrame([], self.output_schema)
            else:
                logging.info(f"FeaturesEngineer: Skipping repartitioning. Current partitions ({current_partitions}) are close to target ({target_partitions}) relative to unique groups.")


            # Process data using applyInPandas
            # Pass the function reference and the broadcast variables
            # We use a lambda function or a partial function to pass extra arguments
            # to the process_group method when it's called by applyInPandas
            processed_df = processed_df.groupBy("interval").applyInPandas(
                lambda pdf: self.process_group(
                    pdf,
                    prev_indicators_broadcast,
                    indicators_config_broadcast,
                    self.mode
                ),
                schema=self.output_schema
            )

            logging.info(f"FeaturesEngineer: Added all indicators in {time.time() - start_time:.2f}s")

            # Unpersist broadcast variables if they are no longer needed
            if prev_indicators_broadcast:
                prev_indicators_broadcast.unpersist()
            if indicators_config_broadcast:
                indicators_config_broadcast.unpersist()

            return processed_df

        except Exception as e:
            logging.error(f"FeaturesEngineer: Error applying indicators: {e}")
            traceback.print_exc()
            # Unpersist broadcast variables in case of error
            if 'prev_indicators_broadcast' in locals() and prev_indicators_broadcast:
                prev_indicators_broadcast.unpersist()
            if 'indicators_config_broadcast' in locals() and indicators_config_broadcast:
                indicators_config_broadcast.unpersist()
            raise # Re-raise the exception after logging and cleanup


if __name__ == "__main__":
    # Test the indicator parsing 
    mode = 'development'
    data_pipeline_config = load_setting(mode)
    postgres_tool = postgres_client.PostgresTools(os.getenv('POSTGRES_URL'))
    indicators_config = postgres_tool.fetch_indicator_set()
    print(indicators_config)