import os
import time
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("ledger.database")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ledger:ledger@localhost:5432/ledger")

# In-memory storage fallback for local standalone testing when Postgres is not running
_IN_MEMORY_RUNS: List[Dict[str, Any]] = [
    {
        "run_id": "run-seeddemo001",
        "sandbox_name": "sbx-seeddemo1",
        "problem_id": "detonator-baseline",
        "state": "deleted",
        "execution_target": "celesto_sandbox",
        "created_at": "2026-10-23T14:20:00Z"
    }
]

def get_connection(max_retries: int = 5, retry_delay: float = 1.0):
    """Obtain a PostgreSQL connection with retry handling."""
    if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
        return None

    last_exc = None
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except Exception as e:
            last_exc = e
            time.sleep(retry_delay)
    logger.warning(f"Failed to connect to PostgreSQL at {DATABASE_URL}: {last_exc}. Falling back to in-memory ledger.")
    return None

def init_db():
    """Ensure runs table exists and seeded record is present."""
    conn = get_connection(max_retries=3, retry_delay=0.5)
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id VARCHAR(255) PRIMARY KEY,
                    sandbox_name VARCHAR(255) NOT NULL,
                    problem_id VARCHAR(255) NOT NULL,
                    state VARCHAR(50) NOT NULL,
                    execution_target VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
                VALUES ('run-seeddemo001', 'sbx-seeddemo1', 'detonator-baseline', 'deleted', 'celesto_sandbox')
                ON CONFLICT (run_id) DO NOTHING;
                """)
                conn.commit()
            logger.info("Database schema initialized and seed verified.")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            conn.rollback()
        finally:
            conn.close()

def list_runs() -> List[Dict[str, Any]]:
    """List all recorded agent runs from the ledger."""
    conn = get_connection(max_retries=1)
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT run_id, sandbox_name, problem_id, state, execution_target, created_at FROM runs ORDER BY created_at ASC;")
                rows = cur.fetchall()
                results = []
                for row in rows:
                    item = dict(row)
                    if isinstance(item.get("created_at"), datetime):
                        item["created_at"] = item["created_at"].isoformat()
                    results.append(item)
                return results
        except Exception as e:
            logger.error(f"Error fetching runs from Postgres: {e}")
        finally:
            conn.close()

    return list(_IN_MEMORY_RUNS)

def insert_run(run_data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a new run row into the ledger."""
    record = dict(run_data)
    if "created_at" not in record or not record["created_at"]:
        record["created_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    conn = get_connection(max_retries=2)
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING run_id, sandbox_name, problem_id, state, execution_target, created_at;
                """, (
                    record["run_id"],
                    record["sandbox_name"],
                    record["problem_id"],
                    record["state"],
                    record["execution_target"]
                ))
                saved = dict(cur.fetchone())
                conn.commit()
                if isinstance(saved.get("created_at"), datetime):
                    saved["created_at"] = saved["created_at"].isoformat()
                return saved
        except Exception as e:
            logger.error(f"Error inserting run to Postgres: {e}")
            conn.rollback()
        finally:
            conn.close()

    # Fallback to memory
    # Check duplicate run_id
    for idx, r in enumerate(_IN_MEMORY_RUNS):
        if r["run_id"] == record["run_id"]:
            _IN_MEMORY_RUNS[idx] = record
            return record
    _IN_MEMORY_RUNS.append(record)
    return record
