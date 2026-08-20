# services/analytics-api/app/analytics/engine.py
"""
Data Analytics Engine — SQL generation + execution.

Orchestrates:
1. Schema context assembly (relevant tables/columns for the query)
2. LLM-based SQL generation
3. SQL safety validation
4. Read-only query execution with timeout
5. Result formatting
"""
import asyncio
import logging
import re
import time

import sqlalchemy as sa
from sqlalchemy import text

from app.analytics.safety import check_cost_guard, sanitize_result, validate_sql
from app.analytics.schema_context import build_schema_prompt
from app.config import Settings
from app.llm import ChatCompletionClient

logger = logging.getLogger(__name__)

# ── SQL Generation Prompt ─────────────────────────────────────────────

_SQL_SYSTEM_PROMPT = """You are an expert PostgreSQL analyst for an e-commerce company (Brazilian marketplace, Olist dataset).

Given the database schema below, write a single PostgreSQL SELECT query to answer the user's question.

Rules:
- Output ONLY the SQL query, no explanation, no markdown fences, no comments.
- Use proper JOINs — always join through order_id as the central key.
- For revenue, use: SUM(olist_order_payments.payment_value)
- For time analysis, use: olist_orders.order_purchase_timestamp
- Use DATE_TRUNC() for grouping by month/quarter/year.
- Always add ORDER BY for sorted results.
- Add LIMIT 100 unless the user asks for all data.
- Use table aliases for readability (o for orders, oi for order_items, etc.).
- Product categories are in Portuguese — use them as-is.
- Filter for order_status = 'delivered' when calculating revenue or delivery metrics.

{schema}
"""


# ── Public API ────────────────────────────────────────────────────────

class AnalyticsEngine:
    """Product-owned text-to-SQL engine with explicit runtime dependencies."""

    def __init__(self, config: Settings, llm_client: ChatCompletionClient):
        self.config = config
        self.llm_client = llm_client
        self._engine: sa.engine.Engine | None = None

    def start(self) -> None:
        db_url = self.config.database_url
        if not db_url:
            logger.warning("Analytics database is not configured")
            return

        db_url = db_url.replace("+asyncpg", "")
        db_url = db_url.replace("?ssl=require", "?sslmode=require")
        db_url = db_url.replace("&ssl=require", "&sslmode=require")
        timeout_ms = self.config.ANALYTICS_QUERY_TIMEOUT * 1_000

        engine_kwargs: dict = {
            "pool_recycle": 300,
        }
        if db_url.startswith("postgresql"):
            engine_kwargs.update(
                pool_size=3,
                max_overflow=2,
                connect_args={
                    "options": (
                        f"-c statement_timeout={timeout_ms} "
                        "-c default_transaction_read_only=on"
                    )
                },
            )
        self._engine = sa.create_engine(db_url, **engine_kwargs)
        logger.info(
            "Analytics engine initialized (timeout=%ds, read_only=on)",
            self.config.ANALYTICS_QUERY_TIMEOUT,
        )

    def close(self) -> None:
        if self._engine:
            self._engine.dispose()

    async def generate_sql(self, query: str) -> str:
        schema_prompt = build_schema_prompt(query)
        system = _SQL_SYSTEM_PROMPT.format(schema=schema_prompt)
        response = await self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
        )
        sql = _clean_sql(response)

        is_safe, error = validate_sql(sql)
        if not is_safe:
            raise ValueError(f"SQL validation failed: {error}")
        is_safe, error = check_cost_guard(sql)
        if not is_safe:
            raise ValueError(f"Cost guard: {error}")
        return sql

    def _execute_sql_sync(self, sql: str) -> dict:
        if self._engine is None:
            raise RuntimeError("Analytics database is not configured")

        start = time.perf_counter()
        with self._engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            raw_rows = [dict(zip(columns, row)) for row in result.fetchall()]
        elapsed_ms = int((time.perf_counter() - start) * 1_000)

        rows, was_truncated = sanitize_result(
            raw_rows, self.config.ANALYTICS_MAX_ROWS
        )
        for row in rows:
            for key, value in row.items():
                if hasattr(value, "isoformat"):
                    row[key] = value.isoformat()
                elif not isinstance(value, (float, int, str, bool, type(None))):
                    row[key] = str(value)

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(raw_rows),
            "time_ms": elapsed_ms,
            "truncated": was_truncated,
        }

    async def execute_sql(self, sql: str) -> dict:
        return await asyncio.to_thread(self._execute_sql_sync, sql)

    async def run(self, query: str) -> dict:
        result = {
            "sql": "",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "time_ms": 0,
            "error": "",
            "truncated": False,
        }
        try:
            sql = await self.generate_sql(query)
            result["sql"] = sql
            result.update(await self.execute_sql(sql))
        except ValueError as exc:
            result["error"] = str(exc)
            logger.warning("Data query validation error: %s", exc)
        except sa.exc.OperationalError as exc:
            error_message = str(exc)
            if "statement timeout" in error_message.lower():
                result["error"] = (
                    "Query timed out after "
                    f"{self.config.ANALYTICS_QUERY_TIMEOUT}s. Try a more specific query."
                )
            else:
                result["error"] = f"Database error: {error_message.split(chr(10))[0]}"
            logger.error("Data query execution error: %s", exc)
        except Exception as exc:
            result["error"] = f"Unexpected error: {exc}"
            logger.error("Data query unexpected error: %s", exc, exc_info=True)
        return result


# ── Helpers ───────────────────────────────────────────────────────────

def _clean_sql(response: str) -> str:
    """Extract clean SQL from LLM response, stripping markdown fences."""
    sql = response.strip()
    # Remove markdown code fences
    sql = re.sub(r'^```(?:sql)?\s*', '', sql, flags=re.MULTILINE)
    sql = re.sub(r'```\s*$', '', sql, flags=re.MULTILINE)
    sql = sql.strip()
    # Remove trailing semicolons
    sql = sql.rstrip(";")
    return sql
