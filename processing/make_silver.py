import time
import pandas as pd
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, lit, array, explode, when, expr
from processing.utilis.resampler import ResampleProcessor
from processing.utilis.add_features import FeaturesEngineer
import traceback
import sys, os
import numpy as np
from dotenv import load_dotenv
from urllib.parse import urlparse
from pyspark.sql.types import StructField, TimestampType, StringType, IntegerType, DoubleType, StructType
import ta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import utilis, postgres_client
from datetime import datetime
from config.load_setting import load_setting

current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(current_dir), '.env')  # Assuming .env is in parent directory

# Load the .env file
load_dotenv(env_path)

POSTGRES_URL = os.getenv('POSTGRES_URL')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

class Processor:
    
    def __init__(self, data_pipeline_config):
        # Load config
        self.postgres_url = POSTGRES_URL
        self.raw_table_name = "raw"
        self.resampled_table_name = "resampled"
        self.resampled_staging_table_name = "resampled_staging"
        self.processed_table_name = "processed"
        self.processed_staging_table_name = "processed_staging"
        self.new_intervals = data_pipeline_config['process']['databatch']['new_intervals']
        self.mode = data_pipeline_config['mode']
        
        # Get the absolute path to the JDBC driver
        current_dir = os.path.dirname(os.path.abspath(__file__))
        jdbc_jar = os.path.join(current_dir, "..", "lib", "postgresql-42.7.2.jar")
        
        if not os.path.exists(jdbc_jar):
            raise FileNotFoundError(f"PostgreSQL JDBC driver not found at {jdbc_jar}")
        
        # Initialize Spark session with JDBC driver
        self.spark = SparkSession.builder \
            .appName("Market Data Processor") \
            .config("spark.executor.memory", "8g") \
            .config("spark.driver.memory", "8g") \
            .config("spark.jars", jdbc_jar) \
            .config("spark.sql.session.timeZone", "UTC") \
            .config("spark.sql.adaptive.enabled", "true") \
            .getOrCreate()
        
        logging.info(f"Initialized Spark session: {self.spark.sparkContext.applicationId}")
        
        # Initialize PostgreSQL connection and JDBC tools
        self.postgres_tool = postgres_client.PostgresTools(POSTGRES_URL)
        self.jdbc_tool = postgres_client.JDBCSparkTools(POSTGRES_URL, self.spark)
    
    def get_data(self):
        """Fetch all symbol data from PostgreSQL and convert to Spark DataFrame"""
        try:
            if self.mode == "reset":
                raw_df = self.jdbc_tool.read_table(self.raw_table_name)
                raw_df = raw_df.filter(col("date") < lit("2025-05-02"))
                return raw_df, None
            elif self.mode == "production":
                                
                # Fetch the latest raw data from the raw table
                latest_raw_df = self.postgres_tool.fetch_latest_symbol_data(self.raw_table_name)
                latest_raw_df = self.spark.createDataFrame(latest_raw_df)

                # Fetch the latest resampled data view from postgres
                latest_resampled_df = self.jdbc_tool.read_table(table_name="latest_resampled")
                latest_resampled_df = latest_resampled_df.repartition(256, "symbol")

                return latest_resampled_df, latest_raw_df

            elif self.mode == "catch_up":
                # Fetch the latest resampled data
                latest_resampled_df = self.jdbc_tool.read_table(self.resampled_table_name)
                latest_resampled_df = latest_resampled_df.repartition(256, "symbol")
                
                # Fetch the latest raw data
                latest_raw_df = self.postgres_tool.fetch_latest_symbol_data(self.raw_table_name)
                latest_raw_df = self.spark.createDataFrame(latest_raw_df)
                
                return latest_resampled_df, latest_raw_df
            else:
                logging.warning("Processor: No data to process")
                exit()
            
        except Exception as e:
            logging.error(f"Processor: Error loading data: {e}")
            traceback.print_exc()
            return None

    def get_processed_data(self):
        """Fetch all processed data from PostgreSQL and convert to Spark DataFrame"""
        processed_cutoff_query = """
            SELECT 
                p.*, 
                latest.latest_date as cutoff_date
            FROM processed p
            JOIN (
                SELECT 
                    symbol, 
                    interval, 
                    MAX(date) AS latest_date
                FROM processed
                GROUP BY symbol, interval
            ) AS latest
            ON p.symbol = latest.symbol 
            AND p.interval = latest.interval
            AND p.date = latest.latest_date
        """
        processed_df = self.jdbc_tool.read_query(processed_cutoff_query)
        
        resampled_cutoff_query = """
            SELECT 
                r.*,
                c.latest_date as cutoff_date
            FROM resampled r
            JOIN (
                SELECT 
                    symbol, 
                    interval,
                    MAX(date) as latest_date
                FROM processed
                GROUP BY symbol, interval
            ) c
            ON r.symbol = c.symbol
            AND r.interval::integer = c.interval::integer  
            AND r.date > c.latest_date
            ORDER BY r.symbol, r.interval, r.date
        """
        resampled_df = self.jdbc_tool.read_query(resampled_cutoff_query)
        return processed_df, resampled_df
    
    def resample(self, df, metadata_df):
        """Resample all symbols with all intervals using Spark's distributed computing"""
        try:
            start_time = time.time()
            logging.info("Processor: Starting bulk resampling for all symbols")
            
            if df is None:
                logging.warning("Processor: No data to process")
                return {}
            
            # Process resampling for all intervals at once
            resampler = ResampleProcessor(self.spark, self.new_intervals, self.mode)
            resampled_df = resampler.apply(df, metadata_df, mode=self.mode)
            
            # Drop the duplicate rows
            resampled_df = resampled_df.dropDuplicates(["date", "symbol", "interval"])
            # Cache the resampled DataFrame
            resampled_df.cache()
            # Save to PostgreSQL efficiently
            if self.mode == "reset":    
                self.save_resampled(resampled_df)   
            elif self.mode == "production":
                # Upsert the resampled data
                self.upsert_resampled(resampled_df)
            elif self.mode == "catch_up":
                # Upsert the resampled data
                self.upsert_resampled(resampled_df)
                
            logging.info(f"Completed all resampling in {time.time() - start_time:.2f}s")
            return resampled_df
        
        except Exception as e:
            logging.error(f"Processor: Error in bulk resampling: {e}")
            traceback.print_exc()
            return False
    
    def truncate_resampled(self):
        self.jdbc_tool.execute_sql(f"TRUNCATE TABLE {self.resampled_staging_table_name}")
    
    def truncate_processed(self):
        self.jdbc_tool.execute_sql(f"TRUNCATE TABLE {self.processed_staging_table_name}")
    
    def upsert_resampled(self, df):
        """Upsert resampled data into main table via staging"""
        try:
            row_count = df.count()
            logging.info(f"Processor: Preparing {row_count} rows for upsert into resampled")

            if row_count == 0:
                logging.warning("Processor: ⚠️ DataFrame is empty — skipping upsert")
                return

            # Clear staging first
            self.truncate_resampled()

            # Write to staging table
            self.jdbc_tool.write_table(df, self.resampled_staging_table_name, "append")

            # Execute upsert
            self.jdbc_tool.upsert_table(
                df=df,
                table_name=self.resampled_table_name,
                staging_table_name=self.resampled_staging_table_name,
                conflict_columns=["date", "symbol", "interval"],
                update_columns=["candle_id", "open", "high", "low", "close", "volume", "type", "status"]
            )

            # Clear staging table
            self.truncate_resampled()
            logging.info("Processor: Cleaned up resampled_staging after upsert")

        except Exception as e:
            logging.error(f"Processor: Error during upsert_resampled: {e}")
            traceback.print_exc()
    
    def save_resampled(self, df):
        self.jdbc_tool.write_table(df, self.resampled_table_name, "append")
    
    def add_indicators(self, resampled_df=None):
        """Process indicators one interval at a time with maximum parallelism"""
        distinct_symbols =  self.postgres_tool.fetch_symbol_count()
        try:
            if self.mode == "reset":
                indicators_config = self.postgres_tool.fetch_indicator_set()
            elif self.mode == "catch_up":
                indicators_config = self.postgres_tool.fetch_indicator_set()
                processed_df, resampled_df = self.get_processed_data()

            all_symbols = resampled_df.select("symbol").distinct().collect()
            for row in all_symbols:
                symbol = row['symbol']
                start_time = time.time()
                logging.info(f"Processor: Adding indicators for symbol: {symbol}")
                
                # Filter just one interval at a time
                temp_processed_df = processed_df.filter(col("symbol") == symbol) if self.mode == "catch_up" else None
                temp_resampled_df = resampled_df.filter(col("symbol") == symbol)
                
                logging.info(f"Processing {distinct_symbols} symbols for symbol {symbol}")
                
                # Repartition conservatively for better parallelism
                partition_count = max(256, distinct_symbols) 
                temp_resampled_df = temp_resampled_df.repartition(partition_count, "symbol")
                temp_processed_df = temp_processed_df.repartition(partition_count, "symbol") if self.mode == "catch_up" else None
                
                # Convert interval to string to avoid type mismatch
                temp_resampled_df = temp_resampled_df.withColumn("interval", col("interval").cast("string"))
                temp_processed_df = temp_processed_df.withColumn("interval", col("interval").cast("string")) if self.mode == "catch_up" else None
                
                # Process all symbols at once
                feature_engineer = FeaturesEngineer(mode=self.mode)

                result_df = feature_engineer.apply(temp_resampled_df, temp_processed_df, indicators_config)
                result_df = result_df.repartition(256, "symbol", "interval", "indicator_id")
                result_df = result_df.sort("symbol", "interval", "indicator_id", "date")
                
                # Drop the duplicate rows
                result_df = result_df.dropDuplicates(["date", "symbol", "interval", "indicator_id"])
                
                # Add error handling for the database write
                try:
                    if self.mode == "reset":
                        # Write results
                        self.save_processed(result_df)
                    elif self.mode == "catch_up":
                        self.upsert_processed(result_df)
                    elapsed_time = time.time() - start_time
                    logging.info(f"Performance: {distinct_symbols/elapsed_time:.2f} symbols/sec")
                    
                except Exception as write_error:
                    logging.error(f"Error writing to database: {write_error}")
                    traceback.print_exc()
                
                # Clean up to free memory
                temp_resampled_df.unpersist(blocking=True)
                temp_processed_df.unpersist(blocking=True) if self.mode == "catch_up" else None
                result_df.unpersist(blocking=True)
                
                # Force garbage collection to reclaim memory
                import gc
                gc.collect()
                
                logging.info(f"Processor: Completed adding indicators for symbol: {symbol}")
                
        except Exception as e:
            logging.error(f"Processor: Error during symbol-wise indicator processing: {e}")
            traceback.print_exc()
    
    def save_processed(self, df):
        self.jdbc_tool.write_table(df, self.processed_table_name, "append", batch_size=5000, num_partitions=256)
    
    def upsert_processed(self, df):
        """Upsert processed data into main table via staging"""
        try:
            row_count = df.count()
            logging.info(f"Processor: Preparing {row_count} rows for upsert into processed")

            if row_count == 0:
                logging.warning("Processor: ⚠️ DataFrame is empty — skipping upsert")
                return

            # Clear staging first
            self.truncate_processed()

            # Write to staging table
            self.jdbc_tool.write_table(df, self.processed_staging_table_name, "append", num_partitions=256)

            # Execute upsert
            self.jdbc_tool.upsert_table(
                df=df,
                table_name=self.processed_table_name,
                staging_table_name=self.processed_staging_table_name,
                conflict_columns=["date", "symbol", "interval", "indicator_id"],
                update_columns=["value"]
            )

            # Clear staging table
            self.truncate_processed()
            logging.info("Processor: Cleaned up processed_staging after upsert")

        except Exception as e:
            logging.error(f"Processor: Error during upsert_processed: {e}")
            traceback.print_exc()
            
    def run(self):
        """Main processing method using Spark"""
        try:
            start_time = time.time()
            logging.info("Processor: Starting Spark-based data processing pipeline...")
            
            # Step 1. Get data
            df, metadata_df = self.get_data()
            
            # Step 2. Resample all symbols at once
            resampled_df = self.resample(df, metadata_df)

            # # Step 3. Process indicators by interval
            # if self.mode == "reset":
            #     self.add_indicators(resampled_df)
            # elif self.mode == "production":
            #     self.spark.catalog.clearCache()
            #     self.add_indicators()
            
            # Log that the pipeline has completed
            logging.info(f"Processor: Completed resampling and indicator processing with total records inserted")
            
        except KeyboardInterrupt:
            logging.warning("Processing interrupted by user")
            return {}
        except Exception as e:
            logging.error(f"Processor: Error in main run: {e}")
            traceback.print_exc()
            return {}
        finally:
            # Ensure we clean up resources
            try:
                self.spark.catalog.clearCache()
                self.postgres_tool.close_connection()
            except:
                pass
    
    def cleanup(self):
        """Clean up Spark resources"""
        if self.spark:
            self.spark.stop()
            logging.info("Spark session stopped")


def main():
    start_time = time.time()
    try:
        mode = 'development'
        data_pipeline_config = load_setting(mode)
        processor = Processor(data_pipeline_config)
        logging.info("Starting Spark-based data processing pipeline...")
        processor.run()
        
        logging.info(f"Data processing completed in {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logging.error(f"Error in data processing: {e}")
        traceback.print_exc()
    finally:
        if processor:
            processor.cleanup()

if __name__ == "__main__":
    main()