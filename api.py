# api.py
import duckdb
from fastapi import FastAPI, Query
from pydantic import BaseModel, RootModel
from typing import List, Any, Optional
import os
from dotenv import load_dotenv

app = FastAPI()

# Load environment variables
load_dotenv()

# Get database credentials
user = os.environ.get('POSTGRES_USER')
password = os.environ.get('POSTGRES_PASSWORD')

# Initialize DuckDB connection
con = duckdb.connect()

# # Install and load postgres scanner
# con.execute("""
#     INSTALL postgres_scanner;
#     LOAD postgres_scanner;
# """)

# Create a view to your PostgreSQL table
con.execute(f"""
    CREATE VIEW raw AS 
    SELECT * FROM postgres_scan(
        'host=localhost port=5432 user={user} password={password} dbname=condvest',
        'public', 'raw'
    );
""")

class Row(RootModel):
    root: List[Any]

class QueryResult(BaseModel):
    columns: List[str]
    rows: List[Row]

@app.get("/resample", response_model=QueryResult)
def resample(
    interval: int = Query(3, description="Resample interval in days"),
    limit: int = Query(50, description="Max rows back"),
    days_back: int = Query(7, description="Days to go back"),
    symbols: Optional[List[str]] = Query(None, description="Filter by symbols (list)")
  ):
    # Build dynamic filters
    where_clauses = [f"date >= NOW() - INTERVAL '{days_back} days'"]
    if symbols:
        sym_list = ", ".join(f"'{s}'" for s in symbols)
        where_clauses.append(f"symbol IN ({sym_list})")
    where_sql = " AND ".join(where_clauses)

    sql = f"""
    WITH ranked AS (
      SELECT *,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date) AS rn
        FROM raw
    ),
    grp AS (
      SELECT *,
        (rn - 1) / {interval} AS grp_id
        FROM ranked
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
    WHERE {where_sql}
    GROUP BY symbol, grp_id
    ORDER BY symbol, date DESC
    LIMIT {limit};
    """
    # execute and grab both column names + native Python lists of tuples
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    data = cur.fetchall()
    return QueryResult(columns=cols, rows=[Row(root=list(r)) for r in data])