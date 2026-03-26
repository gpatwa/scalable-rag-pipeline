#!/usr/bin/env python3
"""
Generic dataset loader for the Data Analytics Agent.

Loads any collection of CSV files into Postgres, auto-discovers schema,
infers types, creates indexes on likely FK columns, and generates
a schema context YAML for the analytics engine.

Usage:
    # Load a directory of CSVs
    python3 scripts/seed_dataset.py data/olist/ --name olist --force

    # Load a single CSV
    python3 scripts/seed_dataset.py data/sales/orders.csv --name sales

    # Load from Kaggle
    python3 scripts/seed_dataset.py --kaggle olistbr/brazilian-ecommerce --name olist

    # Dry run (show what would be loaded, no DB writes)
    python3 scripts/seed_dataset.py data/olist/ --name olist --dry-run

    # Specify a table prefix
    python3 scripts/seed_dataset.py data/hr/ --name hr --prefix hr_

Generated artifacts:
    data/{name}/schema_context.yaml  — schema description for the analytics engine
    data/{name}/.loaded              — marker file (skip re-seed unless --force)
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd
import psycopg2
import sqlalchemy as sa
from sqlalchemy import text

# ── ENV Setup ─────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

if not os.environ.get("DATABASE_URL"):
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    user = os.environ.get("DB_USER", "ragadmin")
    password = os.environ.get("DB_PASSWORD", "changeme")
    db = os.environ.get("DB_NAME", "rag_db")
    os.environ["DATABASE_URL"] = f"postgresql://{user}:{password}@{host}:{port}/{db}"

DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")


# ── Schema Inference ──────────────────────────────────────────────────

def infer_column_type(series: pd.Series) -> str:
    """Map pandas dtype to a human-readable SQL type."""
    dtype = str(series.dtype)
    if "datetime" in dtype:
        return "TIMESTAMP"
    elif "float" in dtype:
        return "NUMERIC"
    elif "int" in dtype:
        return "INTEGER"
    elif "bool" in dtype:
        return "BOOLEAN"
    else:
        max_len = series.astype(str).str.len().max()
        if max_len and max_len > 500:
            return "TEXT"
        return "VARCHAR"


def detect_timestamp_columns(df: pd.DataFrame) -> List[str]:
    """Auto-detect columns that look like timestamps by name or content."""
    ts_cols = []
    for col in df.columns:
        col_lower = col.lower()
        # Name-based detection
        if any(kw in col_lower for kw in ["date", "timestamp", "time", "_at", "_on", "created", "updated"]):
            ts_cols.append(col)
            continue
        # Content-based detection (sample first non-null values)
        if df[col].dtype == "object":
            sample = df[col].dropna().head(5)
            if len(sample) > 0:
                try:
                    pd.to_datetime(sample)
                    ts_cols.append(col)
                except (ValueError, TypeError):
                    pass
    return ts_cols


def detect_fk_columns(df: pd.DataFrame, table_name: str) -> List[str]:
    """Detect likely foreign key columns (end with _id, _key, or _code)."""
    fks = []
    for col in df.columns:
        col_lower = col.lower()
        if col_lower.endswith(("_id", "_key", "_code")) and df[col].dtype == "object":
            fks.append(col)
        elif col_lower.endswith("_id") and "int" in str(df[col].dtype):
            fks.append(col)
    return fks


def detect_relationships(tables: Dict[str, pd.DataFrame]) -> List[dict]:
    """Auto-detect FK relationships between tables by matching column names."""
    relationships = []
    table_names = list(tables.keys())

    for i, (t1_name, t1_df) in enumerate(tables.items()):
        for t2_name, t2_df in list(tables.items())[i + 1:]:
            # Find shared column names (likely join keys)
            shared = set(t1_df.columns) & set(t2_df.columns)
            for col in shared:
                if col.lower().endswith(("_id", "_key", "_code")):
                    relationships.append({
                        "from": f"{t1_name}.{col}",
                        "to": f"{t2_name}.{col}",
                        "type": "many-to-one",
                    })
    return relationships


def generate_column_description(col_name: str, series: pd.Series) -> str:
    """Generate a human-readable description for a column."""
    dtype = infer_column_type(series)
    n_unique = series.nunique()
    n_null = series.isna().sum()
    total = len(series)

    parts = []
    if dtype == "TIMESTAMP":
        parts.append("Date/time field")
    elif col_name.lower().endswith("_id"):
        parts.append(f"Identifier ({n_unique:,} unique values)")
    elif dtype in ("NUMERIC", "INTEGER"):
        if n_null < total:
            non_null = series.dropna()
            parts.append(f"Range: {non_null.min():.2f} to {non_null.max():.2f}")
    elif dtype in ("VARCHAR", "TEXT"):
        if n_unique <= 20 and n_unique > 0:
            top_vals = series.value_counts().head(5).index.tolist()
            parts.append(f"Categories: {', '.join(str(v) for v in top_vals)}")
        else:
            parts.append(f"{n_unique:,} unique values")

    if n_null > 0:
        pct = (n_null / total) * 100
        parts.append(f"{pct:.0f}% null")

    return "; ".join(parts) if parts else f"{dtype} column"


# ── Schema Context YAML Generation ───────────────────────────────────

def generate_schema_yaml(
    dataset_name: str,
    tables: Dict[str, pd.DataFrame],
    table_names: Dict[str, str],
    relationships: List[dict],
    output_dir: Path,
):
    """Generate a schema_context.yaml file describing the dataset."""
    import yaml  # defer import

    schema = {
        "dataset": {
            "name": dataset_name,
            "description": f"Auto-discovered schema for '{dataset_name}' dataset",
            "generated_at": datetime.utcnow().isoformat(),
            "tables": {},
            "relationships": relationships,
            "common_metrics": {},
        }
    }

    for csv_name, df in tables.items():
        table_name = table_names[csv_name]
        table_entry = {
            "description": f"Table '{table_name}' ({len(df):,} rows, {len(df.columns)} columns)",
            "row_count_approx": len(df),
            "columns": {},
            "keywords": _extract_keywords(table_name, df),
        }

        for col in df.columns:
            table_entry["columns"][col] = {
                "type": infer_column_type(df[col]),
                "description": generate_column_description(col, df[col]),
            }

        schema["dataset"]["tables"][table_name] = table_entry

    # Auto-detect common metrics
    schema["dataset"]["common_metrics"] = _detect_metrics(tables, table_names)

    yaml_path = output_dir / "schema_context.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(schema, f, default_flow_style=False, sort_keys=False, width=120)

    print(f"\nSchema context written to: {yaml_path}")
    return yaml_path


def _extract_keywords(table_name: str, df: pd.DataFrame) -> List[str]:
    """Extract search keywords from table name and column names."""
    keywords = set()
    # From table name
    for part in re.split(r'[_\s]+', table_name.lower()):
        if len(part) > 2:
            keywords.add(part)
    # From column names
    for col in df.columns:
        for part in re.split(r'[_\s]+', col.lower()):
            if len(part) > 3 and part not in ("column", "field", "value", "data"):
                keywords.add(part)
    return sorted(keywords)[:15]  # cap at 15


def _detect_metrics(tables: Dict[str, pd.DataFrame], table_names: Dict[str, str]) -> dict:
    """Auto-detect potential business metrics from numeric columns."""
    metrics = {}
    for csv_name, df in tables.items():
        table = table_names[csv_name]
        for col in df.select_dtypes(include=["number"]).columns:
            col_lower = col.lower()
            if any(kw in col_lower for kw in ["price", "value", "amount", "cost", "revenue", "total"]):
                metric_name = f"total_{col}"
                metrics[metric_name] = {
                    "sql": f"SUM({table}.{col})",
                    "description": f"Sum of {col} from {table}",
                }
                metrics[f"avg_{col}"] = {
                    "sql": f"AVG({table}.{col})",
                    "description": f"Average {col} from {table}",
                }
            elif any(kw in col_lower for kw in ["score", "rating", "stars"]):
                metrics[f"avg_{col}"] = {
                    "sql": f"AVG({table}.{col})",
                    "description": f"Average {col} from {table}",
                }
            elif any(kw in col_lower for kw in ["count", "quantity", "qty"]):
                metrics[f"total_{col}"] = {
                    "sql": f"SUM({table}.{col})",
                    "description": f"Total {col} from {table}",
                }
    return metrics


# ── Postgres Loading ──────────────────────────────────────────────────

def load_csvs_to_postgres(
    csv_files: List[Path],
    table_prefix: str,
    force: bool,
    dry_run: bool,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, str]]:
    """
    Load CSV files into Postgres tables.

    Returns:
        (tables dict {csv_name: DataFrame}, table_names dict {csv_name: pg_table_name})
    """
    tables = {}
    table_names = {}

    # Parse DATABASE_URL for psycopg2
    parsed = urlparse(DATABASE_URL)
    pg_conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        user=parsed.username, password=parsed.password,
        dbname=parsed.path.lstrip("/"),
    )
    pg_conn.autocommit = False
    cur = pg_conn.cursor()

    try:
        for csv_path in csv_files:
            # Derive table name from filename
            stem = csv_path.stem.lower()
            # Remove common suffixes
            for suffix in ["_dataset", "_data", "_export", "_dump"]:
                stem = stem.replace(suffix, "")
            table_name = f"{table_prefix}{stem}" if table_prefix else stem
            # Sanitize
            table_name = re.sub(r'[^a-z0-9_]', '_', table_name)

            print(f"  {csv_path.name} → {table_name}", end="", flush=True)

            # Read CSV
            df = pd.read_csv(csv_path, low_memory=False)

            # Auto-detect and parse timestamps
            ts_cols = detect_timestamp_columns(df)
            if ts_cols:
                for col in ts_cols:
                    try:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                    except Exception:
                        pass

            tables[csv_path.name] = df
            table_names[csv_path.name] = table_name

            if dry_run:
                print(f"  ({len(df):,} rows, {len(df.columns)} cols) [DRY RUN]")
                continue

            # Drop and recreate table
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

            cur.execute(f"CREATE TABLE {table_name} ({', '.join(col_defs)})")

            # Use COPY for fast bulk loading
            buf = io.StringIO()
            df.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            cur.copy_expert(
                f"COPY {table_name} FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                buf,
            )
            pg_conn.commit()

            # Auto-create indexes on FK-like columns
            fk_cols = detect_fk_columns(df, table_name)
            for fk_col in fk_cols:
                idx_name = f"idx_{table_name}_{fk_col}"[:63]
                try:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}(\"{fk_col}\")")
                except Exception:
                    pg_conn.rollback()

            # Index timestamp columns for time-series queries
            for ts_col in ts_cols:
                if ts_col in df.columns:
                    idx_name = f"idx_{table_name}_{ts_col}"[:63]
                    try:
                        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}(\"{ts_col}\")")
                    except Exception:
                        pg_conn.rollback()

            pg_conn.commit()
            print(f"  ({len(df):,} rows)")

    finally:
        cur.close()
        pg_conn.close()

    return tables, table_names


# ── Kaggle Download ───────────────────────────────────────────────────

def download_kaggle(dataset_slug: str, output_dir: Path):
    """Download a dataset from Kaggle using the kaggle CLI."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check for existing CSVs
    existing = list(output_dir.glob("*.csv"))
    if existing:
        print(f"Found {len(existing)} existing CSVs in {output_dir}, skipping download.")
        print("Use --force to re-download.")
        return

    print(f"Downloading from Kaggle: {dataset_slug}...")
    try:
        subprocess.run(
            ["kaggle", "datasets", "download", "-d", dataset_slug,
             "-p", str(output_dir), "--unzip"],
            check=True,
        )
    except FileNotFoundError:
        print("Error: 'kaggle' CLI not found. Install with: pip install kaggle")
        print("Configure: https://www.kaggle.com/docs/api")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Kaggle download failed: {e}")
        sys.exit(1)


# ── Dynamic Schema Context Loader ────────────────────────────────────

def generate_python_schema_module(
    dataset_name: str,
    tables: Dict[str, pd.DataFrame],
    table_names: Dict[str, str],
    relationships: List[dict],
    metrics: dict,
    output_dir: Path,
):
    """
    Generate a Python module that the analytics engine can import at runtime.

    This creates data/{name}/schema_context_gen.py which is auto-loaded
    by the analytics engine when ANALYTICS_DATASET={name}.
    """
    lines = [
        f'"""Auto-generated schema context for the {dataset_name} dataset."""',
        f"# Generated at {datetime.utcnow().isoformat()}",
        "",
        "OLIST_SCHEMA = {",
    ]

    for csv_name, df in tables.items():
        tname = table_names[csv_name]
        kws = _extract_keywords(tname, df)
        lines.append(f'    "{tname}": {{')
        lines.append(f'        "description": "Table with {len(df):,} rows, {len(df.columns)} columns",')
        lines.append(f'        "row_count_approx": {len(df)},')
        lines.append(f'        "columns": {{')
        for col in df.columns:
            ctype = infer_column_type(df[col])
            cdesc = generate_column_description(col, df[col]).replace('"', '\\"')
            lines.append(f'            "{col}": {{"type": "{ctype}", "description": "{cdesc}"}},')
        lines.append(f'        }},')
        lines.append(f'        "keywords": {kws},')
        lines.append(f'    }},')

    lines.append("}")
    lines.append("")

    # Relationships
    lines.append(f"TABLE_RELATIONSHIPS = {json.dumps(relationships, indent=4)}")
    lines.append("")

    # Metrics
    lines.append("COMMON_METRICS = {")
    for metric_name, metric_info in metrics.items():
        lines.append(f'    "{metric_name}": {{')
        lines.append(f'        "sql": "{metric_info["sql"]}",')
        lines.append(f'        "description": "{metric_info["description"]}",')
        lines.append(f'    }},')
    lines.append("}")

    py_path = output_dir / "schema_context_gen.py"
    py_path.write_text("\n".join(lines) + "\n")
    print(f"Python schema module written to: {py_path}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Load any CSV dataset into Postgres for the Data Analytics Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/seed_dataset.py data/olist/ --name olist
  python3 scripts/seed_dataset.py data/sales/ --name sales --prefix sales_
  python3 scripts/seed_dataset.py --kaggle olistbr/brazilian-ecommerce --name olist
  python3 scripts/seed_dataset.py data/hr/*.csv --name hr --dry-run
        """,
    )
    parser.add_argument(
        "path", nargs="?",
        help="Path to a CSV file or directory of CSVs",
    )
    parser.add_argument(
        "--name", required=True,
        help="Dataset name (used for directory and schema context)",
    )
    parser.add_argument(
        "--prefix", default="",
        help="Prefix for Postgres table names (e.g. 'hr_')",
    )
    parser.add_argument(
        "--kaggle",
        help="Kaggle dataset slug to download (e.g. 'olistbr/brazilian-ecommerce')",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Drop and recreate tables even if already loaded",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be loaded without writing to DB",
    )

    args = parser.parse_args()

    # Resolve data directory
    data_dir = PROJECT_ROOT / "data" / args.name

    # Kaggle download
    if args.kaggle:
        download_kaggle(args.kaggle, data_dir)

    # Find CSV files
    if args.path:
        path = Path(args.path)
        if path.is_dir():
            csv_files = sorted(path.glob("*.csv"))
        elif path.is_file() and path.suffix.lower() == ".csv":
            csv_files = [path]
        else:
            # Glob pattern
            csv_files = sorted(Path(".").glob(args.path))
    else:
        csv_files = sorted(data_dir.glob("*.csv"))

    if not csv_files:
        print(f"No CSV files found. Provide a path or use --kaggle to download.")
        sys.exit(1)

    # Check loaded marker
    loaded_marker = data_dir / ".loaded"
    if loaded_marker.exists() and not args.force and not args.dry_run:
        print(f"Dataset '{args.name}' already loaded. Use --force to re-seed.")
        return

    print(f"\n{'=' * 60}")
    print(f"Loading dataset: {args.name}")
    print(f"CSV files: {len(csv_files)}")
    print(f"Table prefix: '{args.prefix}' (none)" if not args.prefix else f"Table prefix: '{args.prefix}'")
    print(f"{'=' * 60}\n")

    # Load CSVs
    tables, table_names = load_csvs_to_postgres(
        csv_files, args.prefix, args.force, args.dry_run,
    )

    if not tables:
        print("No tables loaded.")
        return

    # Detect relationships
    relationships = detect_relationships(tables)
    if relationships:
        print(f"\nDetected {len(relationships)} table relationships:")
        for rel in relationships:
            print(f"  {rel['from']} → {rel['to']}")

    # Detect metrics
    metrics = _detect_metrics(tables, table_names)
    if metrics:
        print(f"\nDetected {len(metrics)} potential metrics:")
        for name, info in list(metrics.items())[:10]:
            print(f"  {name}: {info['sql']}")

    # Generate schema context files
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        generate_schema_yaml(args.name, tables, table_names, relationships, data_dir)
    except ImportError:
        print("\nNote: Install PyYAML for YAML schema output: pip install pyyaml")

    generate_python_schema_module(
        args.name, tables, table_names, relationships, metrics, data_dir,
    )

    # Write loaded marker
    if not args.dry_run:
        loaded_marker.write_text(
            f"loaded_at: {datetime.utcnow().isoformat()}\n"
            f"tables: {len(tables)}\n"
            f"total_rows: {sum(len(df) for df in tables.values())}\n"
        )

    # Summary
    total_rows = sum(len(df) for df in tables.values())
    print(f"\n{'=' * 60}")
    print(f"Dataset '{args.name}' loaded successfully!")
    print(f"  Tables: {len(tables)}")
    print(f"  Total rows: {total_rows:,}")
    print(f"  Schema context: data/{args.name}/schema_context.yaml")
    print(f"  Python module: data/{args.name}/schema_context_gen.py")
    print(f"{'=' * 60}")
    print(f"\nNext steps:")
    print(f"  1. Review/edit data/{args.name}/schema_context.yaml")
    print(f"     (add descriptions, fix column names, define business metrics)")
    print(f"  2. Set DATA_ANALYTICS_ENABLED=true in .env")
    print(f"  3. Set ANALYTICS_DATASET={args.name} in .env (optional)")
    print(f"  4. Restart: make dev")


if __name__ == "__main__":
    main()
