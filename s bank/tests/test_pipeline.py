import csv, json, pathlib, sqlite3, tempfile, unittest
from scoach.db import connect, initialize_schema, import_csvs

class PipelineTests(unittest.TestCase):
    def test_bom_selected_rows_refs_metadata_and_immutable_raw(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            (p/'tx_customers_junction.csv').write_text('\ufeffcustomer_id,customer_postal_code,customer_age\nCUST00001,00100,30\nOTHER,00100,20\n', encoding='utf-8')
            (p/'tx_junction_transactions.csv').write_text('customer_id,bank_account_id,tx_date,tx_timestamp,category,tx_amount_eur,balance_after_eur,transaction_type,merchant_id,mcc_code\nCUST00001,A,2026-09-01,01SEP26:10:00:00,Restaurants,-1.005,10,purchase,,\nCUST00001,A,2026-09-01,01SEP26:10:00:00,Restaurants,-1.005,10,purchase,,\nOTHER,B,2026-09-01,01SEP26:10:00:00,Restaurants,-1,10,purchase,,\n')
            conn = connect(p/'demo.sqlite3'); self.addCleanup(conn.close); import_csvs(conn,p)
            rows = conn.execute('select * from transactions').fetchall()
            self.assertEqual(len(rows),2); self.assertNotEqual(rows[0]['transaction_ref'],rows[1]['transaction_ref'])
            self.assertEqual(rows[0]['amount_cents'],-101); self.assertIsNone(rows[0]['merchant_id'])
            run = dict(conn.execute('select * from pipeline_runs').fetchone())
            meta=json.loads(run['source_metadata']); self.assertEqual(meta['tx_junction_transactions.csv']['source_rows'],3)
            self.assertEqual(meta['tx_junction_transactions.csv']['imported_rows'],2)
            self.assertEqual(len(meta['tx_junction_transactions.csv']['sha256']),64)
            with self.assertRaises(sqlite3.IntegrityError): conn.execute('update transactions set amount_cents=0')
            tables={r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
            self.assertTrue({'customers','transactions','mortgage_events','mortgage_final','user_rules','goals','scenarios','scenario_exclusions','audit_events','pipeline_runs'} <= tables)

    def test_malformed_selected_row_is_rejected_and_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            (p/'tx_customers_junction.csv').write_text('customer_id,customer_postal_code,customer_age\nCUST00001,00100,30\n')
            (p/'tx_junction_transactions.csv').write_text('customer_id,bank_account_id,tx_date,tx_timestamp,category,tx_amount_eur,balance_after_eur,transaction_type,merchant_id,mcc_code\nCUST00001,A,2026-09-01,01SEP26:10:00:00,Restaurants,not-money,10,purchase,,\n')
            c=connect(':memory:'); self.addCleanup(c.close)
            import_csvs(c,p)
            self.assertEqual(c.execute('select count(*) from transactions').fetchone()[0],0)
            self.assertEqual(c.execute('select rejected_rows from pipeline_runs').fetchone()[0],1)
