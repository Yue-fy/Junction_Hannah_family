"""Auditable coach state. Actual imported transactions never change."""
import json
from datetime import datetime, timezone
from uuid import uuid4
from .classification import ROLES
from .ledger import account_scope, transactions

PROVENANCE={'user','deterministic','gemini_proposed_user_confirmed'}
STATE_TABLES=('user_rules','goals','scenarios','scenario_exclusions')


def now(): return datetime.now(timezone.utc).isoformat()


def new_id(prefix): return prefix+':'+uuid4().hex


def _snapshot(conn,customer_id):
    return {table:[dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE customer_id=?',(customer_id,))] for table in STATE_TABLES}


def _restore(conn,customer_id,snapshot):
    for table in reversed(STATE_TABLES): conn.execute(f'DELETE FROM {table} WHERE customer_id=?',(customer_id,))
    for table in STATE_TABLES:
        for row in snapshot[table]:
            keys=list(row); conn.execute(f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",[row[k] for k in keys])


def mutate(conn,customer_id,action,scope,operation,provenance='user',reverses=None):
    account_scope(conn,customer_id)
    if provenance not in PROVENANCE: raise ValueError('Invalid provenance')
    with conn:
        before=_snapshot(conn,customer_id); value=operation(); after=_snapshot(conn,customer_id)
        cur=conn.execute('INSERT INTO audit_events(customer_id,timestamp,action,scope,before_json,after_json,provenance,reverses_event_id) VALUES(?,?,?,?,?,?,?,?)',(customer_id,now(),action,scope,json.dumps(before),json.dumps(after),provenance,reverses))
        audit=dict(conn.execute('SELECT * FROM audit_events WHERE id=?',(cur.lastrowid,)).fetchone())
    return value,audit


def _validate_role(role):
    if role not in ROLES: raise ValueError('Unknown role')


def classify_row(conn,customer_id,transaction_ref,role,label=None,provenance='user'):
    _validate_role(role)
    if not transactions(conn,customer_id,filters={'transaction_ref':transaction_ref}): raise ValueError('Row outside customer scope')
    rule={'id':new_id('rule'),'customer_id':customer_id,'kind':'row','transaction_ref':transaction_ref,'category':None,'merchant_id':None,'role':role,'label':label,'provenance':provenance,'created_at':now()}
    def apply():
        conn.execute('INSERT INTO user_rules VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(rule.values())); return rule
    value,audit=mutate(conn,customer_id,'classify_row',transaction_ref,apply,provenance)
    return {**value,'audit_event':audit}


def create_matching_rule(conn,customer_id,category,role,merchant_id=None,label=None,provenance='user'):
    _validate_role(role)
    if not isinstance(category,str) or not category.strip(): raise ValueError('Category required')
    rule={'id':new_id('rule'),'customer_id':customer_id,'kind':'matching','transaction_ref':None,'category':category,'merchant_id':merchant_id,'role':role,'label':label,'provenance':provenance,'created_at':now()}
    def apply():
        conn.execute('INSERT INTO user_rules VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(rule.values())); return rule
    value,audit=mutate(conn,customer_id,'create_matching_rule',category,apply,provenance)
    return {**value,'audit_event':audit}


def undo_last(conn,customer_id,provenance='user'):
    row=conn.execute("SELECT * FROM audit_events a WHERE customer_id=? AND action!='undo' AND NOT EXISTS(SELECT 1 FROM audit_events b WHERE b.reverses_event_id=a.id) ORDER BY id DESC LIMIT 1",(customer_id,)).fetchone()
    if row is None: raise ValueError('Nothing to undo')
    before=json.loads(row['before_json'])
    _,audit=mutate(conn,customer_id,'undo',row['scope'],lambda:_restore(conn,customer_id,before),provenance,row['id'])
    return {'undone_event_id':row['id'],'audit_event':audit}


def reset_demo(conn,customer_id=None,provenance='user'):
    if customer_id is None:
        ids=[r[0] for r in conn.execute('SELECT customer_id FROM customers')]
        return {'customers':[reset_demo(conn,c,provenance) for c in ids]}
    def apply():
        for table in reversed(STATE_TABLES): conn.execute(f'DELETE FROM {table} WHERE customer_id=?',(customer_id,))
    _,audit=mutate(conn,customer_id,'reset_demo','customer',apply,provenance)
    return {'customer_id':customer_id,'reset':True,'audit_event':audit}
