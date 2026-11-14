"""Validated account-scoped, evidence-bearing read model."""
import calendar
import hashlib
import json
from datetime import date, datetime
from .classification import classify


def fact_id(kind, *parts):
    return kind+':'+hashlib.sha256(json.dumps(parts,sort_keys=True,default=str).encode()).hexdigest()[:20]


def month_bounds(month):
    d=date.fromisoformat(month+'-01')
    return d.isoformat(),d.replace(day=calendar.monthrange(d.year,d.month)[1]).isoformat()


def shift_month(month, delta):
    d=date.fromisoformat(month+'-01'); n=d.year*12+d.month-1+delta
    return f'{n//12:04d}-{n%12+1:02d}'


def account_scope(conn, customer_id):
    if not conn.execute('SELECT 1 FROM customers WHERE customer_id=?',(customer_id,)).fetchone():
        raise ValueError('Unknown customer')
    rows=conn.execute('SELECT DISTINCT account_id FROM transactions WHERE customer_id=?',(customer_id,)).fetchall()
    if len(rows)!=1: raise ValueError('Expected exactly one account')
    span=conn.execute('SELECT min(date),max(date) FROM transactions WHERE customer_id=?',(customer_id,)).fetchone()
    return {'customer_id':customer_id,'account_id':rows[0][0],'observed_start':span[0],'observed_end':span[1]}


def transactions(conn, customer_id, start=None, end=None, filters=None):
    scope=account_scope(conn,customer_id); filters=filters or {}
    allowed={'category','role','merchant_id','transaction_type','account_id','transaction_ref'}
    if set(filters)-allowed: raise ValueError('Unsupported transaction filter')
    if filters.get('account_id',scope['account_id'])!=scope['account_id']: raise ValueError('Account outside customer scope')
    for value in (start,end):
        if value: date.fromisoformat(value)
    if start and end and start>end: raise ValueError('Reversed period')
    sql='SELECT * FROM transactions WHERE customer_id=?'; args=[customer_id]
    if start: sql+=' AND date>=?'; args.append(start)
    if end: sql+=' AND date<=?'; args.append(end)
    raw=[dict(r) for r in conn.execute(sql,args)]
    # SAS source timestamps are not lexicographically sortable; ISO date + parsed time is.
    raw.sort(key=lambda r:(r['date'],r['timestamp'].split(':',1)[-1],r['source_line']))
    rules=[dict(r) for r in conn.execute('SELECT * FROM user_rules WHERE customer_id=? ORDER BY created_at,id',(customer_id,))]
    result=[]
    for row in raw:
        matching=[r for r in rules if (r['kind']=='row' and r['transaction_ref']==row['transaction_ref']) or (r['kind']=='matching' and r['category']==row['category'] and (r['merchant_id'] is None or r['merchant_id']==row['merchant_id']))]
        specific=[r for r in matching if r['kind']=='row']
        override=(specific or matching)[-1] if matching else None
        row.update(classify(row,override)); row['source_category']=row['category']; row['observed']=True
        row['fact_id']=fact_id('row',row['transaction_ref'],override)
        if all(row.get(k)==v for k,v in filters.items()): result.append(row)
    return result
