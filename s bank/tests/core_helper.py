"""Fresh coach state over the official ledger, isolated from a running demo."""
from pathlib import Path
from scoach.db import connect, initialize_schema


def demo_connection():
    source=connect(Path(__file__).resolve().parents[1]/'var/scoach.sqlite3')
    target=connect(':memory:'); initialize_schema(target)
    try:
        with target:
            for table in ('customers','transactions','mortgage_final','mortgage_events','pipeline_runs'):
                rows=source.execute(f'SELECT * FROM {table}').fetchall()
                if rows:
                    placeholders=','.join('?' for _ in rows[0])
                    target.executemany(f'INSERT INTO {table} VALUES({placeholders})',[tuple(r) for r in rows])
    finally:
        source.close()
    return target
