import os
import duckdb
from dotenv import load_dotenv
from prefect import get_run_logger

load_dotenv()

class Resampler:
    def __init__(self, settings):
        # Ensure storage/silver directory exists
        silver_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'storage', 'silver')
        os.makedirs(silver_dir, exist_ok=True)
        
        # Set default database file path if not provided
        self.db_file = settings['process']['silver_db_path']
        # Ensure the database file is in the silver directory
        self.db_file = os.path.join(silver_dir, os.path.basename(self.db_file))

        self.con = duckdb.connect(self.db_file)
        self.intervals = settings['process']['new_intervals']
        self.sql_path = settings['process']['sql_path']

        if settings['mode'] == "catch_up":
            self._initialize_raw_data()
        else:
            self._insert_raw_data()

        self.logger = self.get_logger()
        
    def _initialize_raw_data(self):
        """Initialize raw data table from PostgreSQL source"""
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS raw_data AS
            SELECT * FROM postgres_scan(
                'host=localhost port=5432 user={os.getenv("POSTGRES_USER")} password={os.getenv("POSTGRES_PASSWORD")} dbname=condvest',
                'public', 'raw'
            );
        """)
    
    def _insert_raw_data(self):
        """Insert raw data into the raw_data table"""
        # Get the last date from existing raw data
        last_date = self.con.execute("SELECT max(date) FROM raw_data").fetchone()[0]
        # Insert only data after the last date
        self.con.execute(f"""
            INSERT INTO raw_data 
            SELECT * FROM postgres_scan(
                'host=localhost port=5432 user={os.getenv('POSTGRES_USER')} password={os.getenv('POSTGRES_PASSWORD')} dbname=condvest',
                'public', 'raw'
            )
            WHERE date > '{last_date}'
        """)
    
    def get_logger(self):
        return get_run_logger()
    
    def process(self, interval):
        """Create a silver table for a specific interval"""
        import time
        start_time = time.time()
        
        self.logger.info(f"Processor: Processing silver table for interval {interval}")
        table_name = f"silver_{interval}"
        
        # Read the SQL template
        with open(self.sql_path, 'r') as f:
            sql_template = f.read()
        
        # Replace the interval placeholder
        sql_query = sql_template.format(interval=interval)
        
        # Check if the table exists
        exists = self.con.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=?)",
                [table_name]
                ).fetchone()[0]

        if exists:
            self.logger.info(f"Processor: Table '{table_name}' exists.")

            # Get the last date of the silver table
            last_date = self.con.execute(f"SELECT MAX(date) FROM {table_name}").fetchone()[0]
            self.logger.info(f"Processor: Last date of {table_name} is {last_date}")
            
            # Check if there's new raw data that needs to be resampled
            new_raw_data_count = self.con.execute(f"""
                SELECT COUNT(*) FROM raw_data WHERE date > '{last_date}'
            """).fetchone()[0]
            
            if new_raw_data_count > 0:
                self.logger.info(f"Processor: Found {new_raw_data_count} new raw records to resample")
                
                # Get the resampled data for the new period only
                incremental_query = f"""
                    SELECT * FROM ({sql_query})
                    WHERE date > '{last_date}'
                """
                
                # Check if the incremental query returns data
                incremental_count = self.con.execute(f"SELECT COUNT(*) FROM ({incremental_query})").fetchone()[0]
                
                if incremental_count > 0:
                    self.logger.info(f"Processor: Inserting {incremental_count} new resampled records into {table_name}")
                    # Insert new resampled data incrementally
                    self.con.execute(f"""
                        INSERT INTO {table_name}
                        {incremental_query}
                    """)
                else:
                    self.logger.info(f"Processor: No new resampled data to insert into {table_name}")
            else:
                self.logger.info(f"Processor: No new raw data to resample for {table_name}")
        
        else:
            self.logger.info(f"Processor: Table '{table_name}' does not exist.")
            self.logger.info(f"Processor: Creating table {table_name}")
            self.con.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} AS 
                SELECT * FROM ({sql_query})
            """)
            # Create index
            self.con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_date ON {table_name}(symbol, date DESC)")
            
        end_time = time.time()
        execution_time = end_time - start_time
        self.logger.info(f"Processor: Processed silver table for interval {interval} in {execution_time:.2f} seconds")
        
    def run(self):
        """Generate all silver tables for Fibonacci intervals"""
        try:
            for interval in self.intervals:
                self.process(interval)
        finally:
            # Ensure connection is closed
            self.close()

    def close(self):
        """Close the database connection"""
        if hasattr(self, 'con') and self.con:
            self.con.close()
            self.logger.info("Resampler: Database connection closed")

    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
