import os
import duckdb

class MakeSilver:
    def __init__(self, db_file=None):
        self.db_file = db_file or os.getenv("DUCKDB_FILE", "analytics.duckdb")
        self.con = duckdb.connect(self.db_file)
        self._initialize_raw_data()
        
    def _initialize_raw_data(self):
        """Initialize raw data table from PostgreSQL source"""
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS raw_data AS
            SELECT * FROM postgres_scan(
                'host=localhost port=5432 user=… password=… dbname=condvest',
                'public', 'raw'
            );
        """)

    @staticmethod
    def fibonacci(n):
        """Generate Fibonacci sequence up to n numbers"""
        a, b = 1, 1
        fib = [a]
        for _ in range(n-1):
            a, b = b, a + b
            fib.append(a)
        return fib[1:]
    
    def create_silver_table(self, interval):
        """Create a silver table for a specific interval"""
        table_name = f"silver_{interval}m"
        self.con.execute(f"DROP TABLE IF EXISTS {table_name}")
        self.con.execute(f"""
            CREATE TABLE {table_name} AS
            WITH numbered AS (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date) AS rn
            FROM raw_data
            ),
            grp AS (
            SELECT
                *,
                (rn - 1) / {interval} AS grp_id
            FROM numbered
            )
            SELECT
                symbol,
                MIN(date)   AS date,
                FIRST(open) AS open,
                MAX(high)   AS high,
                MIN(low)    AS low,
                LAST(close) AS close,
                SUM(volume) AS volume
            FROM grp
            GROUP BY symbol, grp_id
        """)
        self.con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_date ON {table_name}(symbol, date DESC)")
    
    def generate_all_tables(self, num_intervals=12):
        """Generate all silver tables for Fibonacci intervals"""
        intervals = self.fibonacci(num_intervals)
        for interval in intervals:
            self.create_silver_table(interval)

# Example usage:
if __name__ == "__main__":
    generator = MakeSilver()
    generator.generate_all_tables()