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
        self._initialize_raw_data()
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
        
    def get_logger(self):
        return get_run_logger()
    
    
    def create_silver_table(self, interval):
        """Create a silver table for a specific interval"""
        import time
        start_time = time.time()
        
        self.logger.info(f"Processor: Creating silver table for interval {interval}")
        table_name = f"silver_{interval}"
        
        # Read the SQL template
        with open(self.sql_path, 'r') as f:
            sql_template = f.read()
        
        # Replace the interval placeholder
        sql_query = sql_template.format(interval=interval)
        
        # Create the table if not exists with empty structure
        self.con.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} AS 
            SELECT * FROM ({sql_query})
            WHERE FALSE
        """)
        # Insert new data incrementally
        self.con.execute(f"""
            INSERT INTO {table_name}
            SELECT * FROM ({sql_query})
            WHERE date > (SELECT COALESCE(MAX(date), '1900-01-01') FROM {table_name})
        """)
        
        # Create index
        self.con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_date ON {table_name}(symbol, date DESC)")
        
        end_time = time.time()
        execution_time = end_time - start_time
        self.logger.info(f"Processor: Created silver table for interval {interval} in {execution_time:.2f} seconds")
        
    def run(self):
        """Generate all silver tables for Fibonacci intervals"""

        for interval in self.intervals:
            self.create_silver_table(interval)
