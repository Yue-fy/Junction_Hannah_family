"""End-to-end semantics against independent, inspectable synthetic ledger rows."""
from pathlib import Path
import tempfile
import unittest

from scoach.api import Application
from scoach.db import connect, initialize_schema


class ConversationScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        database = Path(self.directory.name) / 'scope.sqlite3'
        with connect(database) as conn:
            initialize_schema(conn)
            conn.execute("INSERT INTO customers VALUES('C','00100',25,'{}')")
            rows = [
                ('salary-jul', '2026-07-01', 'Salary', 200000, 'salary', None),
                ('restaurant-jul', '2026-07-14', 'Restaurants', -1000, 'purchase', '5812'),
                ('salary-aug', '2026-08-01', 'Salary', 200000, 'salary', None),
                ('restaurant-aug', '2026-08-15', 'Restaurants', -1500, 'purchase', '5812'),
                ('taxi-aug', '2026-08-16', 'Transportation', -3000, 'purchase', '4121'),
                ('bus-aug', '2026-08-17', 'Transportation', -5000, 'purchase', '4111'),
                ('grocery-aug', '2026-08-18', 'Groceries', -2000, 'purchase', '5411'),
                ('salary-sep', '2026-09-01', 'Salary', 200000, 'salary', None),
                ('restaurant-a', '2026-09-02', 'Restaurants', -1200, 'purchase', '5812'),
                ('restaurant-b', '2026-09-20', 'Restaurants', -2800, 'purchase', '5812'),
                ('taxi-sep', '2026-09-03', 'Transportation', -2500, 'purchase', '4121'),
                ('petrol-sep', '2026-09-04', 'Transportation', -8000, 'purchase', '5541'),
                ('pharmacy', '2026-09-05', 'Health', -3000, 'purchase', '5912'),
                ('doctor', '2026-09-06', 'Health', -9000, 'purchase', '8011'),
                ('grocery-sep', '2026-09-07', 'Groceries', -6000, 'purchase', '5411'),
                ('invest-sep', '2026-09-08', 'Invest Deposit', -10000, 'investment_deposit', None),
                ('other-income-sep', '2026-09-09', 'Other Income', 5000, 'other_income', None),
                ('withdrawal-sep', '2026-09-10', 'Invest Withdraw', 7000, 'investment_withdrawal', None),
                ('coverage-end', '2026-09-30', 'Restaurants', -2000, 'purchase', '5812'),
            ]
            balance = 0
            for line, (ref, day, category, amount, kind, mcc) in enumerate(rows, 1):
                balance += amount
                conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             (ref, 'C', 'A', day, day + 'T12:00:00', category, amount, balance,
                              kind, 'M' + str(line), mcc, line, ref, '{}'))
        conn.close()
        self.app = Application(database)

    def ask(self, question, previous=None):
        body = {'customer_id': 'C', 'month': '2026-09', 'message': question, 'locale': 'en'}
        if previous is not None:
            body['previous_query'] = previous
        status, envelope = self.app.handle('POST', '/api/coach', body)
        self.assertEqual(status, 200, envelope)
        return envelope['data']

    def test_validated_model_income_filter_cannot_default_to_zero_outgoing_spending(self):
        for filters,expected,refs in (
            ({'role':'income'},205000,{'salary-sep','other-income-sep'}),
            ({'transaction_type':'salary'},200000,{'salary-sep'}),
            ({'transaction_type':'investment_withdrawal'},7000,{'withdrawal-sep'}),
        ):
            with self.subTest(filters=filters):
                response={'intent':'transaction_statistics','parameters':{'period':'2026-09',**filters},'needs_clarification':False,'explanation_blocks':[]}
                self.app.coach_transport=lambda payload,timeout:response
                result=self.ask('Explain my account')
                self.assertEqual(result['source'],'gemini')
                self.assertEqual(result['query_scope']['metric'],'inflow_total')
                self.assertEqual(result['tool_result']['metric_value_cents'],expected)
                self.assertEqual(set(result['source_refs']['transaction_refs']),refs)
                if filters.get('transaction_type')=='investment_withdrawal':
                    self.assertIn('not earnings',result['tool_result']['definition'])

    def test_optional_language_adapter_can_interpret_a_locally_unrecognized_income_question(self):
        calls=[]
        def transport(payload,timeout):
            calls.append(payload)
            return {'intent':'transaction_statistics','parameters':{'period':'2026-09','role':'income'},'needs_clarification':False,'explanation_blocks':[{'text':'Hier sind die beobachteten Zahlungseingänge.','fact_ids':[payload['context']['facts'][0]['id']]}]}
        self.app.coach_transport=transport
        result=self.ask('Summiere meine Einkünfte.')
        self.assertEqual(len(calls),1)
        self.assertEqual(result['source'],'gemini')
        self.assertEqual(result['tool_result']['metric_value_cents'],205000)
        self.assertEqual(result['query_scope']['metric'],'inflow_total')
        self.assertIn('Zahlungseingänge',result['explanation_blocks'][0]['text'])
        calls.clear()
        limited=self.ask('Did I buy those clothes because I was stressed?')
        self.assertEqual(limited['clarification_code'],'inference_unavailable')
        self.assertEqual(calls,[],'The language adapter must not override a known source limitation')

    def test_taxi_is_only_taxi_not_bus_or_petrol(self):
        result = self.ask('How much did I spend on taxis?')
        self.assertEqual(result['tool_result']['outflow_total_cents'], 2500)
        self.assertEqual(result['tool_result']['transaction_refs'], ['taxi-sep'])
        self.assertEqual(result['query_scope']['filters'], {'mcc_code': '4121'})
        last = self.ask('How much did I spend on taxis last month?')
        self.assertEqual(last['tool_result']['outflow_total_cents'], 3000)
        self.assertEqual(last['tool_result']['transaction_refs'], ['taxi-aug'])

    def test_pharmacy_is_not_doctor_or_all_health(self):
        for message, amount, ref in [('How much did I spend at pharmacies?', 3000, 'pharmacy'),
                                     ('How much did I spend on doctors?', 9000, 'doctor')]:
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertEqual(result['tool_result']['outflow_total_cents'], amount)
                self.assertEqual(result['tool_result']['transaction_refs'], [ref])

    def test_three_turn_followup_keeps_category_and_then_period(self):
        first = self.ask('How much did I spend on restaurants in August 2026?')
        second = self.ask('And groceries?', first['query_scope'])
        third = self.ask('What about September?', second['query_scope'])
        self.assertEqual(first['tool_result']['transaction_refs'], ['restaurant-aug'])
        self.assertEqual(second['tool_result']['transaction_refs'], ['grocery-aug'])
        self.assertEqual(third['tool_result']['transaction_refs'], ['grocery-sep'])
        self.assertEqual([item['tool_result']['outflow_total_cents'] for item in (first, second, third)], [1500, 2000, 6000])

    def test_explicit_range_binds_the_evidence_endpoint_to_identical_rows(self):
        result = self.ask('How much did I spend on restaurants from 2026-08-15 to 2026-09-15?')
        scope = result['query_scope']
        status, rows = self.app.handle('GET', '/api/transactions?customer_id=C&start=' + scope['start'] + '&end=' + scope['end'] + '&category=Restaurants')
        self.assertEqual(status, 200, rows)
        refs = [row['transaction_ref'] for row in rows['data']['transactions']]
        self.assertEqual(refs, ['restaurant-aug', 'restaurant-a'])
        self.assertEqual(refs, result['source_refs']['transaction_refs'])
        self.assertEqual(result['tool_result']['outflow_total_cents'], 2700)

    def test_metrics_return_the_requested_value_instead_of_only_total(self):
        avg = self.ask('What was my average restaurant purchase?')
        count = self.ask('How many restaurant purchases did I make?')
        largest = self.ask('What was my largest restaurant purchase?')
        self.assertEqual(avg['tool_result']['metric_value_cents'], 2000)
        self.assertEqual(count['tool_result']['metric_value_count'], 3)
        self.assertEqual(largest['tool_result']['metric_value_cents'], 2800)
        self.assertEqual(avg['tool_result']['outflow_total_cents'], 6000)

    def test_missing_context_and_unavailable_data_do_not_invent_an_answer(self):
        for question, code in [('And groceries?', 'missing_context'), ('Can I afford it?', 'affordability_context'),
                               ('How much did I spend on coffee?', 'unsupported_detail'),
                               ('What is my average restaurant spending?', 'average_definition'),
                               ('Who is the president?', 'supported_scope')]:
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], code)
                self.assertNotIn('tool_result', result)

    def test_empty_narrow_result_describes_identification_limit(self):
        result = self.ask('How much did I spend on dentists?')
        self.assertEqual(result['tool_result']['transaction_count'], 0)
        self.assertIn('does not prove', result['explanation_blocks'][0]['text'])
        self.assertIsNone(result['tool_result']['average_outflow_cents'])

    def test_changed_account_or_forged_previous_state_is_rejected(self):
        first = self.ask('How much did I spend on restaurants?')['query_scope']
        for changes in [{'customer_id': 'OTHER'}, {'account_id': 'OTHER'}, {'filters': {'sql': 'DELETE'}},
                        {'metric': []}, {'reference_date': []}, {'start': '2026-10-01'}]:
            with self.subTest(changes=changes):
                status, response = self.app.handle('POST', '/api/coach', {
                    'customer_id': 'C', 'month': '2026-09', 'message': 'And groceries?',
                    'previous_query': {**first, **changes}})
                self.assertEqual(status, 400, response)

    def test_direct_mcc_filters_are_exact_and_format_checked(self):
        for endpoint in ('statistics', 'transactions'):
            status, result = self.app.handle('GET', f'/api/{endpoint}?customer_id=C&month=2026-09&mcc_code=4121')
            self.assertEqual(status, 200, result)
            self.assertEqual(result['data']['transaction_refs'], ['taxi-sep'])
            for invalid in ('4121%20OR%201=1', 'abc', '41210'):
                status, response = self.app.handle('GET', f'/api/{endpoint}?customer_id=C&month=2026-09&mcc_code={invalid}')
                self.assertEqual(status, 400, response)

    def test_non_statistics_tools_respect_dates_and_data_boundaries(self):
        tax = self.ask('How much tax did I pay in August?')
        self.assertEqual(tax['parameters']['period'], '2026-08')
        self.assertFalse(tax['tool_result']['available'])
        adjustment = self.ask('How much could I save if I reduced dining out by 20% in August?')
        self.assertEqual(adjustment['tool_result']['actual_total_cents'], 1500)
        self.assertEqual(adjustment['tool_result']['modeled_monthly_contribution_cents'], 300)
        returns = self.ask('What were my investment returns?')
        self.assertTrue(returns['needs_clarification'])
        self.assertEqual(returns['clarification_code'], 'investment_data_limit')
        self.assertNotIn('tool_result', returns)
        goal = self.ask('I want to save for travel')
        self.assertEqual(goal['intent'], 'plan_goal')
        self.assertTrue(goal['needs_clarification'])
        self.assertNotIn('tool_result', goal)

    def test_unsupported_qualifiers_never_silently_change_the_question(self):
        for message in ('How much did I spend on restaurants after refunds?',
                        'How much did I spend on restaurants on weekdays only?',
                        'How much did I spend on restaurants excluding the biggest purchase?',
                        'How much did I spend on restaurants across all my bank accounts?'):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertTrue(result['needs_clarification'])
                self.assertNotIn('tool_result', result)

    def test_new_followup_topic_cannot_reuse_restaurant_filter(self):
        scope = self.ask('How much did I spend on restaurants in August?')['query_scope']
        for message in ('And school fees?', 'And crypto?'):
            with self.subTest(message=message):
                result = self.ask(message, scope)
                self.assertTrue(result['needs_clarification'])
                self.assertNotIn('tool_result', result)
        taxes = self.ask('And taxes?', scope)
        self.assertEqual(taxes['intent'], 'observed_tax_evidence')
        self.assertEqual(taxes['parameters']['period'], '2026-08')
        self.assertFalse(taxes['tool_result']['available'])

    def test_income_salary_and_all_incoming_money_have_distinct_source_definitions(self):
        salary = self.ask('How much salary was credited to my account this month?')
        income = self.ask('How much income did I receive?')
        all_incoming = self.ask('How much money came into my account this month?')
        self.assertEqual(salary['query_scope']['filters'], {'transaction_type': 'salary'})
        self.assertEqual(salary['query_scope']['metric'], 'inflow_total')
        self.assertEqual(salary['tool_result']['metric_value_cents'], 200000)
        self.assertEqual(salary['source_refs']['transaction_refs'], ['salary-sep'])
        self.assertEqual(income['query_scope']['filters'], {'role': 'income'})
        self.assertEqual(income['tool_result']['metric_value_cents'], 205000)
        self.assertEqual(income['source_refs']['transaction_refs'], ['salary-sep', 'other-income-sep'])
        self.assertEqual(all_incoming['query_scope']['filters'], {})
        self.assertEqual(all_incoming['tool_result']['metric_value_cents'], 212000)
        self.assertIn('withdrawal-sep', all_incoming['source_refs']['transaction_refs'])
        self.assertIn('transfer', all_incoming['tool_result']['definition'].lower())

    def test_income_followups_preserve_date_and_change_direction_when_category_changes(self):
        first = self.ask('How much did I spend on restaurants in August?')
        income = self.ask('And income?', first['query_scope'])
        september = self.ask('What about September?', income['query_scope'])
        groceries = self.ask('And groceries?', september['query_scope'])
        self.assertEqual(income['query_scope']['metric'], 'inflow_total')
        self.assertEqual(income['tool_result']['metric_value_cents'], 200000)
        self.assertEqual(income['query_scope']['start'], '2026-08-01')
        self.assertEqual(september['tool_result']['metric_value_cents'], 205000)
        self.assertEqual(groceries['query_scope']['metric'], 'outflow_total')
        self.assertEqual(groceries['tool_result']['metric_value_cents'], 6000)
        last = self.ask('And last month?', september['query_scope'])
        self.assertEqual(last['query_scope']['metric'], 'inflow_total')
        self.assertEqual(last['query_scope']['start'], '2026-08-01')
        self.assertEqual(last['tool_result']['metric_value_cents'], 200000)

    def test_gross_income_and_unsupported_filter_clarifications_offer_executable_questions(self):
        for question in ('What is my gross salary before tax?', 'What is my income tax rate?',
                         'How much did I spend on restaurants on weekdays only?'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertTrue(result['needs_clarification'])
                self.assertTrue(result['clarification_options'])
                followup = self.ask(result['clarification_options'][0])
                self.assertFalse(followup['needs_clarification'])
                self.assertIn('tool_result', followup)

    def test_net_credited_salary_is_supported_but_withholding_is_not_inferred(self):
        for question in ('How much net pay was credited to my account?', 'How much salary after tax was credited to my account?'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertEqual(result['query_scope']['metric'], 'inflow_total')
                self.assertEqual(result['tool_result']['metric_value_cents'], 200000)
                self.assertEqual(result['query_scope']['filters'], {'transaction_type': 'salary'})
        unavailable = self.ask('How much tax was withheld from my salary?')
        self.assertTrue(unavailable['needs_clarification'])
        self.assertEqual(unavailable['clarification_code'], 'income_gross_unavailable')
        self.assertNotIn('tool_result', unavailable)

    def test_income_metrics_and_annual_or_unknown_source_qualifiers_are_not_dropped(self):
        for question in ('What was my average income?', 'What was my largest salary payment?',
                         'How many salary payments did I receive?', 'Montako palkkamaksua sain?',
                         'Vilken var min största lön?', 'How much annual income did I receive?',
                         'How much income did I receive in 2026?', 'How much investment income did I receive?'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertTrue(result['needs_clarification'])
                self.assertNotIn('tool_result', result)

    def test_threshold_and_named_merchant_qualifiers_do_not_widen(self):
        for locale, question in [
            ('en', 'How many restaurant purchases were over 50 euros?'),
            ('fi', 'Montako ravintolaostosta oli yli 50 euroa?'),
            ('sv', 'Hur många restaurangköp var över 50 euro?'),
            ('en', 'How much did I spend on groceries at Prisma?'),
            ('fi', 'Paljonko käytin ruokaostoksiin Prismassa?'),
            ('sv', 'Hur mycket spenderade jag på matvaror hos Prisma?'),
        ]:
            with self.subTest(locale=locale, question=question):
                status, envelope = self.app.handle('POST', '/api/coach', {
                    'customer_id': 'C', 'month': '2026-09', 'locale': locale, 'message': question})
                self.assertEqual(status, 200, envelope)
                result = envelope['data']
                self.assertTrue(result['needs_clarification'])
                self.assertIn(result['clarification_code'], {'unsupported_filter', 'unsupported_detail'})
                self.assertNotIn('tool_result', result)
                self.assertTrue(result['clarification_options'])

    def test_supported_account_date_and_generic_provider_words_remain_available(self):
        for message, total in [('How much did I spend on restaurants from this account?', 6000),
                               ('How much did I spend on restaurants in August?', 1500),
                               ('How much did I spend at pharmacies?', 3000)]:
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['tool_result']['metric_value_cents'], total)

    def test_account_word_does_not_mean_transaction_count(self):
        result = self.ask('How much did I spend on restaurants from this account?')
        self.assertEqual(result['query_scope']['metric'], 'outflow_total')
        self.assertEqual(result['tool_result']['metric_value_cents'], 6000)
        count = self.ask('What is the count of restaurant purchases?')
        self.assertEqual(count['query_scope']['metric'], 'transaction_count')

    def test_total_spending_excludes_transfers_but_money_out_includes_them(self):
        spending = self.ask('How much did I spend this month?')
        self.assertEqual(spending['query_scope']['metric'], 'consumption_total')
        self.assertEqual(spending['tool_result']['metric_value_cents'], 34500)
        self.assertEqual(spending['tool_result']['outflow_total_cents'], 34500)
        self.assertEqual(spending['query_scope']['filters'], {'consumption_only': 'true'})
        self.assertNotIn('invest-sep', spending['source_refs']['transaction_refs'])
        status, rows = self.app.handle('GET', '/api/transactions?customer_id=C&month=2026-09&consumption_only=true')
        self.assertEqual(status, 200, rows)
        self.assertEqual(rows['data']['transaction_refs'], spending['source_refs']['transaction_refs'])
        previous = self.ask('And last month?', spending['query_scope'])
        self.assertEqual(previous['query_scope']['metric'], 'consumption_total')
        self.assertEqual(previous['query_scope']['start'], '2026-08-01')
        money_out = self.ask('How much money left this account?')
        self.assertEqual(money_out['query_scope']['metric'], 'outflow_total')
        self.assertEqual(money_out['tool_result']['metric_value_cents'], 44500)
