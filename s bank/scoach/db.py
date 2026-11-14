"""Reproducible streaming import; immutable source rows, separate coach state."""
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .money import euros_to_cents

DEFAULT_CUSTOMERS = ('CUST00001','CUST00676','CUST05097','CUST00756','CUST00296','CUST01331')
SCHEMA_VERSION = 1


def connect(path):
    if str(path) != ':memory:':
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def initialize_schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS customers(customer_id TEXT PRIMARY KEY, postal_code TEXT, age INTEGER, raw_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS transactions(transaction_ref TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers, account_id TEXT NOT NULL, date TEXT NOT NULL, timestamp TEXT NOT NULL, category TEXT NOT NULL, amount_cents INTEGER NOT NULL, balance_after_cents INTEGER NOT NULL, transaction_type TEXT NOT NULL, merchant_id TEXT, mcc_code TEXT, source_line INTEGER NOT NULL, row_hash TEXT NOT NULL, raw_json TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS tx_scope ON transactions(customer_id,date,timestamp,source_line);
    CREATE TRIGGER IF NOT EXISTS immutable_transactions_update BEFORE UPDATE ON transactions BEGIN SELECT RAISE(ABORT,'Raw transactions are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS immutable_transactions_delete BEFORE DELETE ON transactions BEGIN SELECT RAISE(ABORT,'Raw transactions are immutable'); END;
    CREATE TABLE IF NOT EXISTS mortgage_final(mortgage_customer_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers, raw_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS mortgage_events(event_ref TEXT PRIMARY KEY, mortgage_customer_id TEXT NOT NULL, timestamp TEXT, event_type TEXT, raw_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS user_rules(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers, kind TEXT NOT NULL, transaction_ref TEXT, category TEXT, merchant_id TEXT, role TEXT NOT NULL, label TEXT, provenance TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers, name TEXT NOT NULL, target_cents INTEGER NOT NULL, target_date TEXT NOT NULL, current_saved_cents INTEGER NOT NULL, reserve_floor_cents INTEGER NOT NULL, template TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers, name TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, category TEXT, percent TEXT NOT NULL, goal_id TEXT REFERENCES goals, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS scenario_exclusions(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers, scenario_id TEXT NOT NULL REFERENCES scenarios ON DELETE CASCADE, transaction_ref TEXT NOT NULL REFERENCES transactions, UNIQUE(scenario_id,transaction_ref));
    CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT NOT NULL, timestamp TEXT NOT NULL, action TEXT NOT NULL, scope TEXT NOT NULL, before_json TEXT, after_json TEXT, provenance TEXT NOT NULL, reverses_event_id INTEGER REFERENCES audit_events);
    CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'Audit history is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'Audit history is append-only'); END;
    CREATE TABLE IF NOT EXISTS pipeline_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, imported_at TEXT NOT NULL, schema_version INTEGER NOT NULL, selected_customers TEXT NOT NULL, source_metadata TEXT NOT NULL, rejected_rows INTEGER NOT NULL);
    ''')
    conn.commit()


def import_csvs(conn, source, customer_ids=DEFAULT_CUSTOMERS):
    initialize_schema(conn)
    if conn.execute('SELECT count(*) FROM pipeline_runs').fetchone()[0]:
        raise ValueError('Output already imported; use a fresh database for reproducibility')
    source = Path(source); selected = set(customer_ids); metadata = {}; linked=set(); rejected=0
    names=['tx_customers_junction.csv','tx_junction_transactions.csv','mtg_tx_customer_link_and_final_mtg_infio.csv','mtg_negotiation_history.csv']
    with conn:
        for name in names:
            path=source/name
            if not path.exists():
                if name.startswith('mtg_'): continue
                raise FileNotFoundError(path)
            digest=hashlib.sha256()
            with path.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''): digest.update(chunk)
            meta={'sha256':digest.hexdigest(),'source_rows':0,'imported_rows':0,'rejected_rows':0}; metadata[name]=meta
            with path.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f)
                for line,row in enumerate(reader,2):
                    meta['source_rows']+=1
                    if name != names[3] and row.get('customer_id') not in selected: continue
                    if name == names[3] and row.get('mortgage_customer_id') not in linked: continue
                    raw=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')); row_hash=hashlib.sha256(raw.encode()).hexdigest()
                    try:
                        if name==names[0]:
                            conn.execute('INSERT INTO customers VALUES(?,?,?,?)',(row['customer_id'],row['customer_postal_code'],int(row['customer_age']),raw))
                        elif name==names[1]:
                            datetime.strptime(row['tx_date'],'%Y-%m-%d')
                            conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'tx:{line}:{row_hash}',row['customer_id'],row['bank_account_id'],row['tx_date'],row['tx_timestamp'],row['category'],euros_to_cents(row['tx_amount_eur']),euros_to_cents(row['balance_after_eur']),row['transaction_type'],row['merchant_id'] or None,row['mcc_code'] or None,line,row_hash,raw))
                        elif name==names[2]:
                            linked.add(row['mortgage_customer_id']); conn.execute('INSERT INTO mortgage_final VALUES(?,?,?)',(row['mortgage_customer_id'],row['customer_id'],raw))
                        else:
                            conn.execute('INSERT INTO mortgage_events VALUES(?,?,?,?,?)',(f'mtg:{line}:{row_hash}',row['mortgage_customer_id'],row['timestamp'],row['event_type'],raw))
                        meta['imported_rows']+=1
                    except (ValueError, KeyError, sqlite3.IntegrityError):
                        rejected+=1; meta['rejected_rows']+=1
        conn.execute('INSERT INTO pipeline_runs(imported_at,schema_version,selected_customers,source_metadata,rejected_rows) VALUES(?,?,?,?,?)',(datetime.now(timezone.utc).isoformat(),SCHEMA_VERSION,json.dumps(sorted(selected)),json.dumps(metadata),rejected))
    return metadata
