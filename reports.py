"""
Read-only reporting over analytics.db (guardrail/store.py's `logs` table).
Run manually: python reports.py
"""
import sqlite3

from guardrail.store import DEFAULT_DB_PATH


def total_runs(path: str = DEFAULT_DB_PATH) -> int:
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]


def flag_rate(path: str = DEFAULT_DB_PATH) -> float:
    with sqlite3.connect(path) as conn:
        total, flagged = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN final_decision = 'UNSAFE' THEN 1 ELSE 0 END) FROM logs"
        ).fetchone()
    return (flagged or 0) / total if total else 0.0


def recent_flagged_prompts(limit: int = 10, path: str = DEFAULT_DB_PATH) -> list:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT prompt FROM logs WHERE final_decision = 'UNSAFE' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row[0][:80] for row in rows]


def main():
    print(f"total runs: {total_runs()}")
    print(f"flag rate: {flag_rate():.1%}")
    print("last 10 flagged prompts:")
    for prompt in recent_flagged_prompts():
        print(f"  - {prompt}")


if __name__ == "__main__":
    main()
