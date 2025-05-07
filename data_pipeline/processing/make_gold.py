# Standard library imports
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

# Third-party imports
from dotenv import load_dotenv
from pyspark.sql import SparkSession
import traceback
from processing.utilis.alert_generations import AddTrendAlert
from processing.utilis.signal_generator import VegasChannelSignalGenerator
from pyspark.sql.functions import col, first
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Local imports
from config.load_setting import load_setting
from tools import postgres_client


# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(current_dir), '.env')
load_dotenv(env_path)

# Database configuration
POSTGRES_URL = os.getenv('POSTGRES_URL')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

class SignalsGenerator:
    
    def __init__(self, data_pipeline_config):
        # Load config
        self.postgres_url = POSTGRES_URL
        self.processed_table_name = "processed"
        self.alerts_table_name = "alerts"
        self.signals_table_name = "signals"
        self.new_intervals = data_pipeline_config['process']['databatch']['new_intervals']
        self.reset = data_pipeline_config['mode']
        
        # Get the absolute path to the JDBC driver
        current_dir = os.path.dirname(os.path.abspath(__file__))
        jdbc_jar = os.path.join(current_dir, "..", "lib", "postgresql-42.7.2.jar")
        
        if not os.path.exists(jdbc_jar):
            raise FileNotFoundError(f"PostgreSQL JDBC driver not found at {jdbc_jar}")
        
        # Initialize Spark session with JDBC driver
        self.spark = SparkSession.builder \
            .appName("Alerts Processor") \
            .config("spark.executor.memory", "8g") \
            .config("spark.driver.memory", "8g") \
            .config("spark.jars", jdbc_jar) \
            .config("spark.sql.session.timeZone", "UTC") \
            .config("spark.sql.adaptive.enabled", "true") \
            .getOrCreate()
        
        logging.info(f"Initialized Spark session: {self.spark.sparkContext.applicationId}")
        
        # Parse the PostgreSQL URL to extract components
        parsed_url = urlparse(self.postgres_url)
        host_port = parsed_url.netloc.split('@')[-1]
        database = parsed_url.path.lstrip('/')

        # Set up JDBC properties
        self.jdbc_properties = {
            "driver": "org.postgresql.Driver",
            "user": POSTGRES_USER,
            "password": POSTGRES_PASSWORD,
            "url": f"jdbc:postgresql://{host_port}/{database}",
            "dbtable": self.processed_table_name,
            "batchsize": "1000"
        }
        
        # Set up JDBC properties for alerts table
        self.alerts_jdbc_properties = {
            "driver": "org.postgresql.Driver",
            "user": POSTGRES_USER,
            "password": POSTGRES_PASSWORD,
            "url": f"jdbc:postgresql://{host_port}/{database}",
            "dbtable": self.alerts_table_name,
            "batchsize": "1000"
        }   
        # Set up JDBC properties for signals table
        self.signals_jdbc_properties = {
            "driver": "org.postgresql.Driver",
            "user": POSTGRES_USER,
            "password": POSTGRES_PASSWORD,
            "url": f"jdbc:postgresql://{host_port}/{database}",
            "dbtable": self.signals_table_name,
            "batchsize": "1000"
        }
        # Initialize PostgreSQL connection
        self.postgres_tool = postgres_client.PostgresTools(
            POSTGRES_URL
        )
    
    def get_data(self):
        """Fetch joined processed + resampled + indicator_definitions data for last 5 years via JDBC"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            five_years_ago = (datetime.now() - timedelta(days=5*365)).strftime("%Y-%m-%d")
            query = """
            (
                SELECT 
                    p.date, p.symbol, p.interval, p.value, 
                    i.indicator_id, i.description, r.open, r.high, r.low, r.close, r.volume
                FROM processed AS p
                INNER JOIN resampled AS r 
                    ON p.symbol = r.symbol 
                    AND p.interval::INT = r.interval 
                    AND p.date = r.date
                INNER JOIN indicator_definitions AS i ON p.indicator_id = i.indicator_id
                WHERE p.interval = '1'
                    AND p.date >= NOW() - INTERVAL '5 years'

                ORDER BY p.symbol, p.date desc
            ) AS filtered_joined_data
            """

            df = self.spark.read \
                .format("jdbc") \
                .option("url", self.jdbc_properties["url"]) \
                .option("user", self.jdbc_properties["user"]) \
                .option("password", self.jdbc_properties["password"]) \
                .option("driver", self.jdbc_properties["driver"]) \
                .option("dbtable", query) \
                .option("partitionColumn", "date") \
                .option("lowerBound", five_years_ago) \
                .option("upperBound", today) \
                .option("numPartitions", "10") \
                .option("fetchsize", "1000") \
                .load()
            
            logging.info(f"Processor: Successfully loaded joined data")
            return df

        except Exception as e:
            logging.error(f"Processor: Error loading joined data: {e}")
            traceback.print_exc()
            return None
    
    def pivot_data(self, df):
        """Pivot the dataframe"""
        try:
            pivoted_df = df.groupBy("date", "symbol", "interval") \
                .pivot("description") \
                .agg(first("value"))
        
            olhcv_df = df.select(
                "date", "symbol", "interval", "open", "high", "low", "close", "volume"
                ).dropDuplicates(["date", "symbol", "interval"])

            df = pivoted_df.join(olhcv_df, on=["date", "symbol", "interval"], how="inner")   
            
            df = df.sort("symbol", "interval", "date")
            
            logging.info(f"Processor: Successfully pivoted data")
            return df
        
        except Exception as e:
            logging.error(f"Processor: Error pivoting data: {e}")
            traceback.print_exc()
            return None

    def generate_alerts(self):
        """Add alerts to the data"""
        try:
            start_time = time.time()
            logging.info("Processor: Starting bulk adding alerts and buy/sell signals for all symbols")
            
            # Step 1. Fetch all data at once
            df = self.get_data()
            
            if df is None:
                logging.warning("Processor: No data to process")
                return {}
            
            # Step 2. Pivot the data
            df = self.pivot_data(df)
            
            # Step 3. Add alerts
            alerts_processor = AddTrendAlert(self.spark, df, self.new_intervals)
            alerts_df = alerts_processor.apply()
            
            # Step 4. Sort the alerts by symbol, interval, and date
            alerts_df = alerts_df.sort("symbol", "interval", "date")
            
            logging.info(f"Completed all alerts in {time.time() - start_time:.2f}s")
            return alerts_df
        
        except Exception as e:
            logging.error(f"Processor: Error in generating alerts: {e}")
            traceback.print_exc()
            return False
    
    def generate_signals(self, df):
        """Generate buy/sell signals"""
        try:
            # Apply the signal generator
            signal_generator = VegasChannelSignalGenerator(df, self.new_intervals)
            signals_df = signal_generator.apply() 
            
            logging.info(f"Processor: Successfully generated signals")
            return signals_df
        
        except Exception as e:
            logging.error(f"Processor: Error in generating signals: {e}")
            traceback.print_exc()
            return False
    
    def save_alerts(self, df):
        """Save alerts to PostgreSQL"""
        try:
            # Save to PostgreSQL efficiently
            df.write \
                .format("jdbc") \
                .mode("append") \
                .options(**self.alerts_jdbc_properties) \
                .save()
            
            logging.info(f"Processor: Successfully saved alerts")
            return df
        
        except Exception as e:
            logging.error(f"Processor: Error in saving alerts: {e}")
    
    def save_signals(self, df):
        """Save signals to PostgreSQL"""
        try:
            # Save to PostgreSQL efficiently
            df.write \
                .format("jdbc") \
                .mode("append") \
                .options(**self.signals_jdbc_properties) \
                .save()

            logging.info(f"Processor: Successfully saved signals")
            return df
        
        except Exception as e:
            logging.error(f"Processor: Error in saving signals: {e}")
    
    def run(self):
        """Main processing method using Spark"""
        try:
            logging.info("Processor: Starting Spark-based data processing pipeline...")
            
            # Step 1. Add alerts to the data
            alerts_df = self.generate_alerts()
            
            # Step 2. Save alerts to PostgreSQL 
            self.save_alerts(alerts_df)
            
            # Step 3. Generate signals
            signals_df = self.generate_signals(alerts_df)
            
            # Step 4. Save signals to PostgreSQL
            self.save_signals(signals_df)
            
            # Log that the pipeline has completed
            logging.info(f"Processor: Completed alerts AND buy/sell signals processing with total records inserted")
            
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
        
        signals_generator = SignalsGenerator(data_pipeline_config)
        logging.info("Starting Spark-based data processing pipeline...")
        signals_generator.run()
        
        logging.info(f"Data processing completed in {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logging.error(f"Error in data processing: {e}")
        traceback.print_exc()
    finally:
        if signals_generator:
            signals_generator.cleanup()

if __name__ == "__main__":
    main()