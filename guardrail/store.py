"""
SQLite logging for pipeline runs. Called from cli.py (the shell), never from
inside process_prompt() or the judges — logging is an I/O side effect, and
the guardrail core stays pure per the project's one rule (no I/O in core).
"""
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB_PATH = "analytics.db"


def init_db(path: str = DEFAULT_DB_PATH) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                prompt TEXT,
                local_filter_result TEXT,
                input_verdict TEXT,
                output_verdict TEXT,
                final_decision TEXT,
                model_used TEXT
            )
            """
        )


def log_interaction(
    prompt: str,
    local_result: str,
    input_verdict: str,
    output_verdict: str,
    final_decision: str,
    model_used: str,
    path: str = DEFAULT_DB_PATH,
) -> None:
    # every value is bound as a "?" placeholder, never string-formatted into
    # the SQL text — that's what makes this safe against SQL injection even
    # though `prompt` is arbitrary user input.
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO logs (
                timestamp, prompt, local_filter_result, input_verdict,
                output_verdict, final_decision, model_used
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                prompt,
                local_result,
                input_verdict,
                output_verdict,
                final_decision,
                model_used,
            ),
        )
