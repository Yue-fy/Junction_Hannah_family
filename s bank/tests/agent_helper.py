"""Small synthetic ledger for agent tests; never opens the demo database."""
import copy
import tempfile
import unittest
from pathlib import Path

from scoach.db import connect, initialize_schema


class AgentFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'test.sqlite3'
        self.conn = connect(self.database)
        self.addCleanup(self.conn.close)
        initialize_schema(self.conn)
        self.customer = 'CUST_TEST'
        self.conn.execute('INSERT INTO customers VALUES(?,?,?,?)',
                          (self.customer, '00100', 30, '{}'))
        balance = 100_000
        index = 0
        for month in range(1, 10):
            for day, category, amount, kind, merchant, mcc in [
                (1, 'Salary', 200_000, 'salary', None, None),
                (2, 'Housing', -60_000, 'housing_payment', None, None),
                (3, 'Utilities', -5_000, 'utilities_payment', None, None),
                (10, 'Groceries', -10_000, 'purchase', 'M1', '5411'),
                (15, 'Restaurants', -2_570, 'purchase', 'M2', '5812'),
                (20, 'Restaurants', -20_000, 'purchase', 'M3', '5812'),
                (25, 'Transportation', -1_300, 'purchase', 'M4', '4121'),
                (28, 'Savings', -10_000, 'salary_sweep', None, None),
            ]:
                index += 1
                balance += amount
                self.conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (f'tx:{index}:private', self.customer, 'ACC_TEST',
                     f'2026-{month:02d}-{day:02d}', '15SEP26:12:00:00', category,
                     amount, balance, kind, merchant, mcc, index, 'private-hash', '{}'))
        self.conn.commit()


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []

    def __call__(self, contents, **kwargs):
        self.requests.append(copy.deepcopy({'contents': contents, **kwargs}))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


def call(tool_name, **args):
    return {'role': 'model', 'parts': [{'functionCall': {'name': tool_name, 'args': args}}]}


def answer(text):
    return {'role': 'model', 'parts': [{'text': text}]}
