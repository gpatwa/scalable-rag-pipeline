#!/usr/bin/env python3
"""
Seed script for Olist Brazilian E-Commerce dataset.

Downloads (or expects) CSV files in data/olist/ and loads them
into PostgreSQL tables for the Data Analytics Agent.

Usage:
    # Place CSVs in data/olist/ first (download from Kaggle)
    python3 scripts/seed_olist.py
    python3 scripts/seed_olist.py --force   # re-seed (drops and recreates tables)

Kaggle dataset: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
"""
import os
import sys
from pathlib import Path

import csv
import io

import pandas as pd
import psycopg2
import sqlalchemy as sa

# Load .env if available
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Build DATABASE_URL from components if not set
if not os.environ.get("DATABASE_URL"):
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    user = os.environ.get("DB_USER", "ragadmin")
    password = os.environ.get("DB_PASSWORD", "changeme")
    db = os.environ.get("DB_NAME", "rag_db")
    os.environ["DATABASE_URL"] = f"postgresql://{user}:{password}@{host}:{port}/{db}"

DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
engine = sa.create_engine(DATABASE_URL)

DATA_DIR = Path(__file__).parent.parent / "data" / "olist"

# CSV filename → table name mapping
CSV_TABLE_MAP = {
    "olist_customers_dataset.csv": "olist_customers",
    "olist_orders_dataset.csv": "olist_orders",
    "olist_order_items_dataset.csv": "olist_order_items",
    "olist_order_payments_dataset.csv": "olist_order_payments",
    "olist_order_reviews_dataset.csv": "olist_order_reviews",
    "olist_products_dataset.csv": "olist_products",
    "olist_sellers_dataset.csv": "olist_sellers",
    "olist_geolocation_dataset.csv": "olist_geolocation",
}

# Columns that should be parsed as timestamps
TIMESTAMP_COLS = {
    "olist_orders": [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "olist_order_items": ["shipping_limit_date"],
    "olist_order_reviews": ["review_creation_date", "review_answer_timestamp"],
}

# Indexes to create for query performance
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_orders_customer ON olist_orders(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_purchase_ts ON olist_orders(order_purchase_timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON olist_orders(order_status)",
    "CREATE INDEX IF NOT EXISTS idx_items_order ON olist_order_items(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_items_product ON olist_order_items(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_items_seller ON olist_order_items(seller_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_order ON olist_order_payments(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_order ON olist_order_reviews(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_category ON olist_products(product_category_name)",
    "CREATE INDEX IF NOT EXISTS idx_geo_zip ON olist_geolocation(geolocation_zip_code_prefix)",
]


def check_csvs_exist() -> bool:
    """Check if all required CSV files are present."""
    missing = []
    for csv_name in CSV_TABLE_MAP.keys():
        if not (DATA_DIR / csv_name).exists():
            missing.append(csv_name)
    if missing:
        print(f"Missing CSV files in {DATA_DIR}:")
        for f in missing:
            print(f"  - {f}")
        print(f"\nDownload from: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce")
        print(f"Place all CSV files in: {DATA_DIR}/")
        return False
    return True


def seed():
    """Load Olist CSVs into Postgres tables."""
    if not check_csvs_exist():
        sys.exit(1)

    force = "--force" in sys.argv

    # Check if already seeded
    with engine.connect() as conn:
        try:
            result = conn.execute(sa.text("SELECT COUNT(*) FROM olist_orders"))
            count = result.scalar()
            if count > 0 and not force:
                print(f"Olist tables already have data ({count:,} orders). Use --force to re-seed.")
                return
        except Exception:
            conn.rollback()  # Reset failed transaction

    if force:
        print("Dropping existing Olist tables...")
        with engine.connect() as conn:
            for table_name in reversed(list(CSV_TABLE_MAP.values())):
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
            conn.commit()

    # Load each CSV using psycopg2 directly (fast COPY, pandas 3.x compatible)
    print(f"\nLoading Olist dataset from {DATA_DIR}...\n")
    total_rows = 0

    # Parse DATABASE_URL for psycopg2
    from urllib.parse import urlparse
    parsed = urlparse(DATABASE_URL)
    pg_conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        user=parsed.username, password=parsed.password,
        dbname=parsed.path.lstrip("/"),
    )
    pg_conn.autocommit = False
    cur = pg_conn.cursor()

    try:
        for csv_name, table_name in CSV_TABLE_MAP.items():
            csv_path = DATA_DIR / csv_name
            print(f"Loading {csv_name}...", end=" ", flush=True)

            df = pd.read_csv(csv_path, low_memory=False)

            # Parse timestamp columns
            parse_dates = TIMESTAMP_COLS.get(table_name, [])
            for col in parse_dates:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors="coerce")

            # Drop table and recreate with inferred types
            cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

            # Build CREATE TABLE from DataFrame
            col_defs = []
            for col in df.columns:
                dtype = str(df[col].dtype)
                if "datetime" in dtype:
                    sql_type = "TIMESTAMP"
                elif "float" in dtype:
                    sql_type = "DOUBLE PRECISION"
                elif "int" in dtype:
                    sql_type = "BIGINT"
                else:
                    sql_type = "TEXT"
                col_defs.append(f'"{col}" {sql_type}')

            create_sql = f"CREATE TABLE {table_name} ({', '.join(col_defs)})"
            cur.execute(create_sql)

            # Use COPY for fast bulk loading
            buf = io.StringIO()
            df.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            cur.copy_expert(
                f"COPY {table_name} FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                buf,
            )
            pg_conn.commit()

            row_count = len(df)
            total_rows += row_count
            print(f"{row_count:,} rows")

        # Create indexes
        print("\nCreating indexes...")
        for idx_sql in INDEXES:
            try:
                cur.execute(idx_sql)
            except Exception as e:
                pg_conn.rollback()
                print(f"  Warning: {e}")
        pg_conn.commit()

    finally:
        cur.close()
        pg_conn.close()

    print(f"\nOlist dataset loaded! {total_rows:,} total rows across {len(CSV_TABLE_MAP)} tables.")
    print("\nTo enable the data analytics agent:")
    print("  1. Set DATA_ANALYTICS_ENABLED=true in .env")
    print("  2. Restart: make dev")
    print("  3. Ask: 'What was the revenue trend by month?'")


if __name__ == "__main__":
    seed()
