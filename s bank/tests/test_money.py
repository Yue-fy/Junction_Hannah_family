import unittest
from scoach.money import euros_to_cents, cents_to_euros, percentile_cents

class MoneyTests(unittest.TestCase):
    def test_half_up_and_nearest_rank(self):
        self.assertEqual(euros_to_cents('1.005'), 101)
        self.assertEqual(euros_to_cents('-1.005'), -101)
        self.assertEqual(cents_to_euros(-101), '-1.01')
        self.assertEqual(percentile_cents([1, 2, 3, 4], .25), 1)
        self.assertEqual(percentile_cents([1, 2, 3, 4], .5), 2)
        with self.assertRaises(ValueError): percentile_cents([], .25)

    def test_even_median_and_invalid_nonfinite_money(self):
        from scoach.money import median_cents
        self.assertEqual(median_cents([100,101]),101)
        self.assertEqual(median_cents([-100,-101]),-101)
        for value in ('NaN','Infinity','-Infinity'):
            with self.assertRaises(ValueError): euros_to_cents(value)

    def test_malformed_money_raises_validation_error(self):
        with self.assertRaises(ValueError): euros_to_cents('not-money')
