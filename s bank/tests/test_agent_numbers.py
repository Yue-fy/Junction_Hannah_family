import unittest


class AgentNumberTests(unittest.TestCase):
    def test_compact_scientific_and_unknown_money_suffixes_do_not_bypass_check(self):
        from scoach.agent_numbers import unverified_numbers
        for text in ('€9k', 'EUR 9k', 'EUR9k', '€1.2m', '€1e9', '€9bn', '9k euros', '€1.2 million', '€1e9999999'):
            with self.subTest(text=text):
                self.assertTrue(unverified_numbers(text))
        self.assertEqual(unverified_numbers('€9k', [{'total_cents': 900000}]), [])

    def test_model_authored_labels_and_proposals_are_not_numeric_evidence(self):
        from scoach.agent_numbers import unverified_numbers
        result = {'name': 'Budget €8765.43', 'basis': 'Try €8765.43', 'proposal': {'name': '€8765.43'}, 'required_monthly_cents': 10000}
        self.assertEqual(unverified_numbers('€8765.43', [result]), ['8765.43'])
        self.assertEqual(unverified_numbers('€100', [result]), [])

    def test_localized_money_percentages_counts_and_dates(self):
        from scoach.agent_numbers import unverified_numbers
        results = [{'total_cents': 187866, 'saving_cents': 4514, 'percent': '20', 'count': 18}]
        for text in ('€1,878.66; €45.14; 20%; 18 payments.',
                     '1 878,66 €; 45,14 €; 20 %; 18 maksua.',
                     '1\u00a0878,66 €; 45,14 €; 20 %; 18 köp.',
                     '€1,879, on 30 September 2026 and 2026-09-30.'):
            with self.subTest(text=text):
                self.assertEqual(unverified_numbers(text, results, '', [], {'start': '2026-09-01', 'end': '2026-09-30'}), [])
        self.assertEqual(unverified_numbers('€999.99 and 21%', results), ['999.99', '21'])

    def test_user_numbers_history_and_cent_conversion_are_distinct(self):
        from scoach.agent_numbers import unverified_numbers
        self.assertEqual(unverified_numbers('€500.00 and 32%', [], 'I have €500',
            [{'role': 'user', 'text': 'Use 32%'}]), [])
        self.assertEqual(unverified_numbers('€22570', [{'total_cents': 22570}]), ['22570'])
        self.assertEqual(unverified_numbers('€22,570.00', [{'total_cents': 22570}]), ['22570.00'])

    def test_unverified_small_currency_is_not_exempt_like_sentence_numbers(self):
        from scoach.agent_numbers import unverified_numbers
        self.assertEqual(unverified_numbers('Three baskets, 2 ideas in 2026.'), [])
        self.assertEqual(unverified_numbers('Spend €9 or 8%.', []), ['9', '8'])
        self.assertEqual(unverified_numbers('Spend 9 euros or 8 percent.', []), ['9', '8'])

    def test_rounding_tolerance_and_negative_values(self):
        from scoach.agent_numbers import unverified_numbers
        self.assertEqual(unverified_numbers('-€45.14 and 45.15', [{'delta_cents': -4514}, {'total_cents': 4514}]), [])
        self.assertEqual(unverified_numbers('45.16', [{'total_cents': 4514}]), ['45.16'])


from scoach.agent_numbers import unverified_numbers


class ApproximationAndTrimTests(unittest.TestCase):
    def test_sourced_percentages_may_be_rounded(self):
        results = [{'share_percent': '67.4'}]
        self.assertEqual(unverified_numbers('About 67% went to must-pays.', results), [])
        self.assertEqual(unverified_numbers('Exactly 67.4% went to must-pays.', results), [])
        self.assertEqual(unverified_numbers('About 70% went to must-pays.', results), ['70'])

    def test_approximate_euros_need_an_approximation_word(self):
        results = [{'total_cents': 187866}]
        self.assertEqual(unverified_numbers('You spent about €1,900 this month.', results), [])
        self.assertEqual(unverified_numbers('Noin 1 900 € kului.', results), [])
        self.assertEqual(unverified_numbers('You spent €1,900 this month.', results), ['1900'])
        self.assertEqual(unverified_numbers('You spent about €2,000 this month.', results), ['2000'])

    def test_second_violation_keeps_only_verified_sentences(self):
        from scoach.agent import _without_unverified
        results = [{'total_cents': 22570}]
        text = 'You spent €225.70 on eating out. That is 31% of your spending. Small changes add up.'
        self.assertEqual(_without_unverified(text, results, '', (), {}), 'You spent €225.70 on eating out. Small changes add up.')
        self.assertEqual(_without_unverified('That is 31% of your spending.', results, '', (), {}), '')
