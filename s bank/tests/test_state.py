import unittest
from tests.core_helper import demo_connection
from scoach.ledger import transactions
from scoach.state import classify_row, create_matching_rule, undo_last, reset_demo

class StateTests(unittest.TestCase):
    def setUp(self): self.c=demo_connection()
    def tearDown(self): self.c.close()
    def test_correction_rule_audit_undo_preserve_source(self):
        row=transactions(self.c,'CUST00001','2026-09-01','2026-09-30',{'category':'Restaurants'})[0]
        ref=row['transaction_ref']; before=self.c.execute('select raw_json from transactions where transaction_ref=?',(ref,)).fetchone()[0]
        result=classify_row(self.c,'CUST00001',ref,'flexible_essential',label='Tax')
        self.assertEqual(result['audit_event']['provenance'],'user')
        changed=transactions(self.c,'CUST00001',filters={'transaction_ref':ref})[0]
        self.assertEqual(changed['role'],'flexible_essential'); self.assertEqual(changed['source_category'],'Restaurants')
        undo_last(self.c,'CUST00001')
        self.assertEqual(transactions(self.c,'CUST00001',filters={'transaction_ref':ref})[0]['role'],'discretionary')
        self.assertEqual(self.c.execute('select count(*) from audit_events').fetchone()[0],2)
        self.assertEqual(self.c.execute('select raw_json from transactions where transaction_ref=?',(ref,)).fetchone()[0],before)
        create_matching_rule(self.c,'CUST00001','Restaurants','fixed_obligation',label='User tax')
        self.assertEqual(transactions(self.c,'CUST00001',filters={'transaction_ref':ref})[0]['role'],'fixed_obligation')
        with self.assertRaises(ValueError): classify_row(self.c,'CUST00001',ref,'made_up')
        with self.assertRaises(ValueError): classify_row(self.c,'CUST00676',ref,'discretionary')
        reset_demo(self.c,'CUST00001')
        self.assertEqual(self.c.execute('select count(*) from user_rules').fetchone()[0],0)
        self.assertEqual(self.c.execute('select count(*) from audit_events').fetchone()[0],4)
    def test_persistence_across_sqlite_connection_and_undo_reset(self):
        import pathlib,tempfile
        from scoach.db import connect
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)/'state.sqlite3'; persisted=connect(path); self.c.backup(persisted)
            create_matching_rule(persisted,'CUST00001','Restaurants','flexible_essential'); persisted.close()
            persisted=connect(path)
            self.assertEqual(persisted.execute('select count(*) from user_rules').fetchone()[0],1)
            reset_demo(persisted,'CUST00001'); undo_last(persisted,'CUST00001')
            self.assertEqual(persisted.execute('select count(*) from user_rules').fetchone()[0],1); persisted.close()

    def test_audit_history_rejects_direct_update_or_delete(self):
        import sqlite3
        from scoach.db import initialize_schema
        initialize_schema(self.c)
        create_matching_rule(self.c,'CUST00001','Restaurants','discretionary')
        with self.assertRaises(sqlite3.IntegrityError): self.c.execute("update audit_events set provenance='deterministic'")
        with self.assertRaises(sqlite3.IntegrityError): self.c.execute('delete from audit_events')
