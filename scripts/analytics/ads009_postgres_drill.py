"""Run the ADS-009 control-store drill against a disposable PostgreSQL database."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2 import errors


def main() -> None:
    database_url = os.environ.get("ADS009_DATABASE_URL")
    if not database_url:
        raise SystemExit("ADS009_DATABASE_URL is required")

    prefix = f"ads009-{uuid.uuid4().hex[:12]}"
    run_id = f"{prefix}-run"
    connection = psycopg2.connect(database_url)
    connection.autocommit = False
    cursor = connection.cursor()
    try:
        cursor.execute(
            """INSERT INTO analytics_agent_runs
            (run_id, tenant_id, purpose, graph_version, state_version, current_node, state_payload)
            VALUES (%s, 'tenant-live', 'm0-drill', 'fake-v1', 'v1', 'create', '{}'::jsonb)""",
            (run_id,),
        )
        cursor.execute(
            """INSERT INTO analytics_run_leases
            (run_id, tenant_id, owner_id, lease_token, fencing_seq, expires_at)
            VALUES (%s, 'tenant-live', 'worker-a', %s, 1, %s)""",
            (run_id, f"{prefix}-lease-a", datetime.now(timezone.utc) + timedelta(minutes=5)),
        )
        cursor.execute(
            """INSERT INTO analytics_run_checkpoints
            (run_id, checkpoint_seq, tenant_id, graph_version, state_version, current_node,
             transition_seq, lease_fencing_seq, state_payload)
            VALUES (%s, 1, 'tenant-live', 'fake-v1', 'v1', 'bootstrap', 1, 1,
                    '{"step":"bootstrap"}'::jsonb)""",
            (run_id,),
        )
        cursor.execute(
            """INSERT INTO analytics_run_transitions
            (run_id, transition_seq, tenant_id, from_node, to_node, from_status, to_status,
             fencing_seq, idempotency_key, evidence_payload)
            VALUES (%s, 1, 'tenant-live', 'create', 'bootstrap', 'active', 'active', 1, %s, '{}'::jsonb)""",
            (run_id, f"{prefix}-transition-1"),
        )
        connection.commit()

        cursor.execute(
            """UPDATE analytics_run_leases
            SET owner_id='worker-b', lease_token=%s, fencing_seq=2, renewed_at=CURRENT_TIMESTAMP
            WHERE run_id=%s AND fencing_seq=1""",
            (f"{prefix}-lease-b", run_id),
        )
        assert cursor.rowcount == 1
        cursor.execute(
            """UPDATE analytics_agent_runs SET lease_fencing_seq=2
            WHERE run_id=%s AND lease_fencing_seq < 2""",
            (run_id,),
        )
        assert cursor.rowcount == 1
        connection.commit()

        cursor.execute(
            """UPDATE analytics_agent_runs SET current_node='retrieve', transition_seq=2
            WHERE run_id=%s AND lease_fencing_seq <= 1""",
            (run_id,),
        )
        assert cursor.rowcount == 0, "stale worker unexpectedly committed"
        connection.rollback()

        try:
            cursor.execute(
                "UPDATE analytics_run_transitions SET to_node='tampered' WHERE run_id=%s AND transition_seq=1",
                (run_id,),
            )
            connection.commit()
            raise AssertionError("append-only trigger did not reject mutation")
        except errors.RaiseException:
            connection.rollback()

        dedupe_key = f"{prefix}-outbox-once"
        cursor.execute(
            """INSERT INTO analytics_run_outbox
            (tenant_id, run_id, event_type, dedupe_key, payload)
            VALUES ('tenant-live', %s, 'checkpoint', %s, '{}'::jsonb)""",
            (run_id, dedupe_key),
        )
        connection.commit()
        try:
            cursor.execute(
                """INSERT INTO analytics_run_outbox
                (tenant_id, run_id, event_type, dedupe_key, payload)
                VALUES ('tenant-live', %s, 'checkpoint', %s, '{}'::jsonb)""",
                (run_id, dedupe_key),
            )
            connection.commit()
            raise AssertionError("outbox dedupe did not reject duplicate")
        except errors.UniqueViolation:
            connection.rollback()

        first = psycopg2.connect(database_url)
        second = psycopg2.connect(database_url)
        try:
            first_cursor = first.cursor()
            second_cursor = second.cursor()
            first_cursor.execute(
                """SELECT id FROM analytics_run_outbox
                WHERE dedupe_key=%s AND delivery_status='queued'
                FOR UPDATE SKIP LOCKED LIMIT 1""",
                (dedupe_key,),
            )
            assert first_cursor.fetchone() is not None
            second_cursor.execute(
                """SELECT id FROM analytics_run_outbox
                WHERE dedupe_key=%s AND delivery_status='queued'
                FOR UPDATE SKIP LOCKED LIMIT 1""",
                (dedupe_key,),
            )
            assert second_cursor.fetchone() is None, "second claimant did not skip locked row"
            second.rollback()
            first.commit()
        finally:
            first.close()
            second.close()
    finally:
        connection.close()

    print("ADS-009 live PostgreSQL drill: PASS")
    print("fencing_cas=pass")
    print("append_only_transition=pass")
    print("outbox_dedupe=pass")
    print("skip_locked_contention=pass")
    print(f"run_id={run_id}")


if __name__ == "__main__":
    main()
