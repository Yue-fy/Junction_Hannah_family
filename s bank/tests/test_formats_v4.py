"""V4 lane N: number formats (money, percent, VAT rate) and localized tax sentences."""
import unittest
from decimal import Decimal

from scoach.db import connect, initialize_schema
from scoach.money import format_euro, format_percent
from scoach.tax import tax_overview, tax_texts
from scoach.vat import _rate_label, rate_label_texts


class FormatTests(unittest.TestCase):
    def test_money(self):
        self.assertEqual(format_euro(113827), '€1,138.27')
        self.assertEqual(format_euro(113827, 'fi'), '1 138,27 €')
        self.assertEqual(format_euro(113827, 'sv'), '1 138,27 €')
        self.assertEqual(format_euro(-22570, 'fi'), '-225,70 €')
        self.assertEqual(format_euro(113850, 'en', 0), '€1,139')
        with self.assertRaises(ValueError):
            format_euro(1.5)

    def test_percent(self):
        self.assertEqual(format_percent('9.63'), '9.6%')
        self.assertEqual(format_percent('9.63', 'fi'), '9,6 %')
        self.assertEqual(format_percent(Decimal('1E+1'), 'en', 0), '10%')
        self.assertEqual(format_percent(Decimal('1E+1')), '10.0%')

    def test_vat_rate_never_scientific(self):
        self.assertEqual(_rate_label(1000), '10%')
        self.assertEqual(_rate_label(1350), '13.5%')
        self.assertEqual(_rate_label(2550), '25.5%')
        self.assertEqual(rate_label_texts(1350), {'en': '13.5%', 'fi': '13,5 %', 'sv': '13,5 %'})
        self.assertNotIn('E', _rate_label(1000))


class TaxTextTests(unittest.TestCase):
    def setUp(self):
        self.c = connect(':memory:'); initialize_schema(self.c)
        self.c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        balance = 0
        for i, month in enumerate(range(1, 10)):
            balance += 250000
            self.c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           ('s%d' % i, 'C', 'A', '2026-%02d-15' % month, '01X26:12:00:00', 'Salary', 250000, balance, 'salary', None, None, i, 'h', '{}'))
        self.c.commit()

    def tearDown(self):
        self.c.close()

    def test_flow_has_thousands_separators_in_every_language(self):
        w = tax_overview(self.c, 'C', '2026-09-30', {'tax_year': 2026, 'base_rate_bp': 2400, 'gross_monthly_cents': 340000})['overview']['withholding']
        texts = w['flow']['texts']
        self.assertIn('€30,600.00', texts['en'])
        self.assertIn('30 600,00 €', texts['fi']); self.assertIn('Brutto', texts['fi'])
        self.assertIn('30 600,00 €', texts['sv'])
        self.assertEqual(w['flow']['text'], texts['en'])

    def test_back_tax_tasks_localized_with_local_dates(self):
        cycle = tax_overview(self.c, 'C', '2026-09-30', {'tax_year': 2025, 'decision_result': 'back_tax', 'decision_amount_cents': 123456,
                                                          'decision_due_dates': ['2026-12-01', '2027-02-01']})['overview']['cycle']
        self.assertEqual(cycle['stage_label_texts']['fi'], 'Jäännösveroa maksettavana')
        self.assertIn('1 234,56 €', cycle['task_texts']['fi'][0])
        self.assertIn('1.12.2026', cycle['task_texts']['fi'][1])
        self.assertIn('1 dec 2026', cycle['task_texts']['sv'][1])
        self.assertEqual(cycle['task_texts']['en'], cycle['tasks'])
        for locale in ('fi', 'sv'):
            for line in cycle['task_texts'][locale]:
                self.assertNotIn('MyTax', line)

    def test_every_fixed_sentence_has_three_languages(self):
        from scoach import tax
        for sentence in tax._TAX_TEXT:
            if '%s' not in sentence:
                texts = tax_texts(sentence)
                self.assertEqual(texts['en'], sentence)
                self.assertTrue(texts['fi'] and texts['sv'])


if __name__ == '__main__':
    unittest.main()
