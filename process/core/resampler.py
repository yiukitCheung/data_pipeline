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

            # Get the last date of the table
            last_date = self.con.execute(f"SELECT MAX(date) FROM {table_name}").fetchone()[0]
            self.logger.info(f"Processor: Last date of {table_name} is {last_date}")
            # Get the last date of the new data
            last_date_new_data = self.con.execute(f"SELECT MAX(date) FROM ({sql_query})").fetchone()[0]
            self.logger.info(f"Processor: Last date of new data is {last_date_new_data}")
            # If the last date of the new data is greater than the last date of the table, insert the new data
            if last_date_new_data > last_date:
                self.logger.info(f"Processor: Inserting new data into {table_name}")
                # Insert new data incrementally
                self.con.execute(f"""
                    INSERT INTO {table_name}
                    SELECT * FROM ({sql_query})
                    WHERE date > '{last_date}'
                """)
            else:
                self.logger.info(f"Processor: No new data to insert into {table_name}")
        
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
        for interval in self.intervals:
            self.process(interval)
