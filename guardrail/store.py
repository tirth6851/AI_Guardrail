"""
SQLite logging for pipeline runs. Called from the shell (cli.py), never from
inside the core — logging is I/O, and the guardrail core stays pure.

CHANGE FROM M4: the log used to store the raw prompt verbatim, which made the
audit database itself a PII store (trust boundary TB5). Now:
- the `prompt` column holds the PII-REDACTED prompt (emails/SSNs/etc. replaced
  with [LABEL] placeholders via pii.redact).
- a new `prompt_hash` column holds a salted SHA-256 of the ORIGINAL prompt, so
  repeat/abuse detection can still group identical prompts without storing their
  content. Set GUARDRAIL_HASH_SALT in the environment; the default is a clearly
  non-secret placeholder so a misconfig is obvious.
"""
import hashlib
import os
import sqlite3
from datetime import datetime, timezone

from guardrail import pii

DEFAULT_DB_PATH = "analytics.db"
_SALT = os.getenv("GUARDRAIL_HASH_SALT", "CHANGE-ME-dev-salt")


def _hash(prompt: str) -> str:
    return hashlib.sha256((_SALT + prompt).encode("utf-8")).hexdigest()


def init_db(path: str = DEFAULT_DB_PATH) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                prompt TEXT,             -- PII-redacted, never raw
                prompt_hash TEXT,        -- salted SHA-256 of the original
                local_filter_result TEXT,
                input_verdict TEXT,
                output_verdict TEXT,
                final_decision TEXT,
                model_used TEXT
            )
            """
        )
        # lightweight migration: a DB created before the hardening pass has no
        # prompt_hash column, and CREATE TABLE IF NOT EXISTS won't add it. Add it
        # in place so an existing analytics.db keeps working without data loss.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(logs)")}
        if "prompt_hash" not in existing:
            conn.execute("ALTER TABLE logs ADD COLUMN prompt_hash TEXT")


def log_interaction(
    prompt: str,
    local_result: str,
    input_verdict: str,
    output_verdict: str,
    final_decision: str,
    model_used: str,
    path: str = DEFAULT_DB_PATH,
) -> None:
    # redact before storing; hash the original for dedup. every value is still a
    # "?" placeholder — never string-formatted into SQL — so arbitrary prompt
    # text can't inject SQL.
    redacted, _ = pii.redact(prompt)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO logs (
                timestamp, prompt, prompt_hash, local_filter_result,
                input_verdict, output_verdict, final_decision, model_used
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                redacted,
                _hash(prompt),
                local_result,
                input_verdict,
                output_verdict,
                final_decision,
                model_used,
            ),
        )
