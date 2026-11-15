"""Regression tests for the four problems in docs/critique/live_v4_eval.md (live DeepSeek eval, Alex, Sep 2026).

The live model is not reachable in tests, so each live answer is fed through the same verifier and trimmer
the agent uses. The answer texts are the live drafts as far as the eval notes quote them, completed into
whole answers with Alex's real plan figures (30 Sep 2026: €38.47 a day, €269.29 this week, payday 15 Oct).
"""
import copy
import unittest

from scoach.agent import _is_fragment, _sentences, _without_unverified, build_system_prompt, run_agent
from scoach.agent_numbers import allowed_numbers, unverified_numbers
from scoach.agent_tools import ToolContext, dispatch

from agent_helper import AgentFixture, ScriptedTransport, answer, call

# Alex's safe_to_spend result as the tool gives it now (V5): one set of figures, free-choice part hidden.
LIVE_SAFE = {
    'evidence_id': 'ev1', 'as_of': '2026-09-30', 'balance_cents': 472358, 'next_payday': '2026-10-15',
    'days_to_payday': 14, 'held_back': [
        {'kind': 'bill', 'label': 'Rent', 'amount_cents': 52838, 'date': '2026-10-05'},
        {'kind': 'buffer', 'label': 'Surprise costs (health, repairs)', 'amount_cents': 20458, 'date': None},
        {'kind': 'reserve', 'label': 'Small safety cushion', 'amount_cents': 50000, 'date': None}],
    'held_back_cents': 123296, 'everyday_cents': 31145, 'buffer_cents': 20458, 'reserve_floor_cents': 50000,
    'shortfall_cents': 0, 'daily_life_cents': 57711, 'per_day_cents': 3847, 'this_week_cents': 26929,
    'this_week_days': 7, 'extra_cents': 291351, 'safe_to_save_cents': 291351, 'planned_saving_cents': 0,
}
# The same result in the V4 shape the live eval ran on (free-choice part and free money visible).
LIVE_SAFE_V4 = {**LIVE_SAFE, 'spendable_until_payday_cents': 26566, 'free_cents': 317917}
SCOPE = {'start': '2026-09-01', 'end': '2026-09-30', 'reference_date': '2026-09-30'}
# Note: days_to_payday is 14 above (not Alex's 15) so a bare "15" is never verified by coincidence;
# only the payday date 2026-10-15 can verify "15.10." / "15 okt".

FI02 = ('Voit käyttää turvallisesti noin 38,47 € päivässä palkkapäivään 15.10. asti. Tällä viikolla se tekee 269,29 €. '
        'Koko loppujakson turvallinen summa on 265,66 €, ja laskut, puskuri ja pieni varmuusvara on jo varattu.')
FI03 = ('Voit käyttää 38,47 € päivässä 15.10. asti. Toinen hyvä uutinen: 2 913,51 € voisi siirtää säästöön. '
        'Arvio perustuu aiempiin menoihisi, ei ole takuu.')
FI04 = ('Talous on hallinnassa. 15.10. asti voit käyttää 38,47 € päivässä, eli 269,29 € tällä viikolla. '
        'Vuokra 528,38 € ja puskuri on jo varattu.')
SV02 = ('Du kan använda 38,47 € per dag fram till lönedagen 15 okt. Den här veckan blir det 269,29 €. '
        'Totalt har du 265,66 € att röra dig med.')
SV03 = ('Fram till 15.10. kan du använda 38,47 € per dag. Totalt har du 265,66 € att röra dig med. '
        'Hyran och bufferten är redan avsatta.')
EN03 = ('You can safely spend about €38.47 a day, roughly €269.29 this week, until payday on 15 Oct. '
        'That leaves €265.66 in total spending money until payday.')


def trim(text, results=(LIVE_SAFE,), message='', history=()):
    return _without_unverified(text, list(results), message, list(history), SCOPE)


class FinnishAndSwedishDatesAreVerified(unittest.TestCase):
    """Problem 1a: "15.10." / "15.10.2026" / "15 okt" are dates checked against tool dates, not the decimal 15.10."""

    def test_live_lead_sentences_now_verify(self):
        for text in ('Voit käyttää turvallisesti noin 38,47 € päivässä palkkapäivään 15.10. asti.',
                     'Talous on hallinnassa. 15.10. asti voit käyttää 38,47 € päivässä, eli 269,29 € tällä viikolla.',
                     'Palkkapäivä on 15.10.2026.', 'Du kan använda 38,47 € per dag fram till lönedagen 15 okt.',
                     'Fram till 15.10. kan du använda 38,47 € per dag.', 'Lönen kommer 15 oktober.'):
            with self.subTest(text=text):
                self.assertEqual(unverified_numbers(text, [LIVE_SAFE], '', [], SCOPE), [])

    def test_the_whole_v4_drafts_verify_in_the_shape_they_were_written_for(self):
        # In V4 every figure in these drafts came from a tool; only the date failed ("15.1").
        for text in (FI02, FI03, FI04, SV02, SV03):
            with self.subTest(text=text[:30]):
                self.assertEqual(unverified_numbers(text, [LIVE_SAFE_V4], '', [], SCOPE), [])

    def test_a_date_that_no_tool_gave_is_still_flagged(self):
        self.assertEqual(unverified_numbers('Voit käyttää 38,47 € päivässä 16.10. asti.', [LIVE_SAFE], '', [], SCOPE), ['16.10.'])
        self.assertEqual(unverified_numbers('Palkka tulee 15.10.2027.', [LIVE_SAFE], '', [], SCOPE), ['15.10.2027'])
        # A date the customer wrote may be repeated.
        self.assertEqual(unverified_numbers('Sinulla on 38,47 € päivässä 20.10. asti.', [LIVE_SAFE], 'Riittääkö 20.10. asti?', [], SCOPE), [])

    def test_euro_decimals_are_never_read_as_dates(self):
        for text in ('Se maksaa 15.10 €.', 'It costs €15.10.', 'Spent 15.10, then more.'):
            with self.subTest(text=text):
                self.assertEqual(unverified_numbers(text, [LIVE_SAFE], '', [], SCOPE), ['15.10'])
        self.assertEqual(unverified_numbers('It costs €15.10.', [{'amount_cents': 1510}]), [])


class SentencesAreNeverCutAtADate(unittest.TestCase):
    """Problem 1b: the splitter kept "asti." / "asti voit käyttää…" as separate sentences."""

    def test_no_split_inside_a_date(self):
        self.assertEqual(_sentences(FI02)[0], 'Voit käyttää turvallisesti noin 38,47 € päivässä palkkapäivään 15.10. asti.')
        self.assertEqual(_sentences(FI04)[1], '15.10. asti voit käyttää 38,47 € päivässä, eli 269,29 € tällä viikolla.')
        self.assertEqual(_sentences('Maksu 15. lokakuuta asti. Sitten palkka.'), ['Maksu 15. lokakuuta asti.', 'Sitten palkka.'])
        # A date at a real sentence end still ends the sentence.
        self.assertEqual(_sentences('Palkka tulee 15.10. Sitä ennen 38,47 € päivässä.'),
                         ['Palkka tulee 15.10.', 'Sitä ennen 38,47 € päivässä.'])
        self.assertEqual(_sentences('About €38.47 a day. That is €269.29 this week.'),
                         ['About €38.47 a day.', 'That is €269.29 this week.'])

    def test_trimmed_live_answers_keep_their_lead_and_never_start_mid_sentence(self):
        cases = {
            'fi02': (FI02, 'Voit käyttää turvallisesti noin 38,47 € päivässä palkkapäivään 15.10. asti. Tällä viikolla se tekee 269,29 €.'),
            'fi03': (FI03, FI03),
            'fi04': (FI04, FI04),
            'sv02': (SV02, 'Du kan använda 38,47 € per dag fram till lönedagen 15 okt. Den här veckan blir det 269,29 €.'),
            'sv03': (SV03, 'Fram till 15.10. kan du använda 38,47 € per dag. Hyran och bufferten är redan avsatta.'),
        }
        for name, (draft, expected) in cases.items():
            with self.subTest(case=name):
                trimmed = trim(draft)
                self.assertEqual(trimmed, expected)
                self.assertFalse(any(piece.startswith('asti') for piece in _sentences(trimmed)))
                self.assertTrue(trimmed[0].isupper() or trimmed[0].isdigit())

    def test_fragments_are_dropped_after_trimming(self):
        for fragment in ('asti.', 'asti voit käyttää 38,47 € päivässä.', 'Kiva juttu.', '  '):
            with self.subTest(fragment=fragment):
                self.assertTrue(_is_fragment(fragment))
        self.assertFalse(_is_fragment('15.10. asti voit käyttää 38,47 € päivässä.'))
        self.assertFalse(_is_fragment('Talous on hallinnassa.'))
        # The V4 split pieces themselves never survive a trim.
        self.assertEqual(trim('Talous on hallinnassa. asti voit käyttää 38,47 € päivässä. Tällä viikolla se tekee 269,29 €.'),
                         'Talous on hallinnassa. Tällä viikolla se tekee 269,29 €.')

    def test_end_to_end_a_finnish_trimmed_answer_keeps_the_dated_lead(self):
        fixture = _Fixture()
        fixture.setUp()
        try:
            draft = 'Voit käyttää 5,00 € päivässä palkkapäivään 1.10. asti. Koko summa on 99,99 €.'
            fake = ScriptedTransport(call('safe_to_spend'), answer(draft), answer(draft))
            result = run_agent(fixture.conn, fixture.customer, '2026-09', 'fi', 'Paljonko voin käyttää?', [], transport=fake)
        finally:
            fixture.doCleanups()
        self.assertEqual(result['source'], 'agent')
        self.assertEqual(result['verification'], 'trimmed')
        self.assertEqual(result['answer'], ['Voit käyttää 5,00 € päivässä palkkapäivään 1.10. asti.'])


class _Fixture(AgentFixture):
    def runTest(self):
        pass


class OneSetOfSpendingFigures(AgentFixture):
    """Problem 2 (en03): €38.47 a day next to "€265.66 in total spending money" (only the free-choice part)."""

    def tool(self, name, **args):
        ctx = ToolContext(self.conn, self.customer, '2026-09', message='What can I safely spend this week?')
        return dispatch(self.conn, self.customer, ctx, name, args)

    def test_tool_shows_per_day_daily_life_this_week_and_extra_only(self):
        from scoach import forecast
        raw = forecast.spending_plan(self.conn, self.customer, '2026-09-28')
        for name in ('safe_to_spend', 'safe_to_save'):
            with self.subTest(tool=name):
                result = self.tool(name)
                for key in ('per_day_cents', 'daily_life_cents', 'this_week_cents', 'extra_cents'):
                    self.assertEqual(result[key], raw[key], key)
                self.assertEqual(result['per_day_cents'], result['daily_life_cents'] // result['days_to_payday'])
                for hidden in ('spendable_until_payday_cents', 'spendable_until_payday', 'spendable_cents', 'free_cents', 'free'):
                    self.assertNotIn(hidden, result)
                self.assertIn('daily_life is the one total until payday', result['rule'])
                self.assertFalse(any('until payday)' in text for text in result['assumptions']))

    def test_the_free_choice_part_can_no_longer_be_quoted_as_the_total(self):
        result = self.tool('safe_to_spend')
        # Live: €265.66 was the free-choice part; €577.11 (daily_life) is the real total.
        live = copy.deepcopy(LIVE_SAFE)
        self.assertEqual(unverified_numbers(EN03, [live], '', [], SCOPE), ['265.66'])
        self.assertEqual(unverified_numbers(EN03.replace('€265.66 in total spending money', '€577.11 in total for daily life'),
                                            [live], '', [], SCOPE), [])
        self.assertEqual(trim(EN03), 'You can safely spend about €38.47 a day, roughly €269.29 this week, until payday on 15 Oct.')
        self.assertNotIn('free_cents', result)

    def test_prompt_names_daily_life_as_the_total(self):
        ctx = ToolContext(self.conn, self.customer, '2026-09')
        system, _, _ = build_system_prompt(self.conn, self.customer, ctx, '2026-09', 'en', [])
        self.assertIn('The total until\n  payday is daily_life_cents', system)
        self.assertIn('Never call any\n  other figure the total or "spending money"', system)
        self.assertIn('extra_cents, "could be saved"', system)


class LifeEventAnswerStillHelps(AgentFixture):
    """Problem 3 (en08): "I've drafted a note about the job change for you to review…" and nothing else."""

    def test_prompt_requires_warmth_and_a_practical_step_with_the_note(self):
        ctx = ToolContext(self.conn, self.customer, '2026-09')
        system, _, _ = build_system_prompt(self.conn, self.customer, ctx, '2026-09', 'en', [])
        self.assertIn('Calling propose_profile_update never replaces the answer', system)
        self.assertIn('one warm sentence, then one\n  practical step from their own data', system)
        self.assertIn('the per-day amount until payday and that the buffer\n  is kept aside', system)
        self.assertIn('there is a note for them to review', system)

    def test_the_tool_result_reminds_the_model_to_answer(self):
        ctx = ToolContext(self.conn, self.customer, '2026-09', message='I just lost my job. What should I do?')
        result = dispatch(self.conn, self.customer, ctx, 'propose_profile_update',
                          {'entries': [{'key': 'life_event', 'value': '{"type":"job_loss","since":"2026-09"}'}]})
        self.assertFalse(result['saved'])
        self.assertIn('Still answer the customer: one warm sentence', result['answer_still_needed'])
        self.assertEqual(len(ctx.actions), 1)

    def test_a_full_job_loss_answer_passes_the_number_check(self):
        text = ("I'm really sorry about your job; that is a lot to take in. For now, about €38.47 a day until "
                "payday on 15 Oct keeps you steady, with the buffer still kept aside. I've drafted a note about "
                "the job change for you to review.")
        self.assertEqual(unverified_numbers(text, [LIVE_SAFE], '', [], SCOPE), [])


class CategoryNamesAreLocalized(AgentFixture):
    """Problem 4 (fi06): an English "(Lifestyle)" inside a Finnish answer."""

    def test_tools_give_localized_category_names(self):
        ctx = ToolContext(self.conn, self.customer, '2026-09', message='Millainen kuluttaja olen?')
        result = dispatch(self.conn, self.customer, ctx, 'explore',
                          {'start': '2026-01-01', 'end': '2026-09-30', 'group_by': 'category'})
        self.assertEqual(result['category_names']['Restaurants'], {'en': 'Eating out', 'fi': 'Ravintolat', 'sv': 'Restauranger'})
        profile = dispatch(self.conn, self.customer, ctx, 'spender_profile', {})
        for key in profile.get('category_names', {}):
            self.assertIn(key, profile['category_names'])
        from scoach.agent_tools import _category_names
        self.assertEqual(_category_names({'why': [{'category': 'Lifestyle', 'text': 'Your largest bigger purchase was €354.21 (Lifestyle).'}]}),
                         {'Lifestyle': {'en': 'Shopping', 'fi': 'Ostokset', 'sv': 'Shopping'}})
        # Labels carry no numbers that could verify a figure.
        self.assertEqual(allowed_numbers([{'category_names': {'X': {'fi': '42 €'}}}]), set())

    def test_prompt_asks_for_the_answer_language_name(self):
        ctx = ToolContext(self.conn, self.customer, '2026-09')
        system, _, _ = build_system_prompt(self.conn, self.customer, ctx, '2026-09', 'fi', [])
        self.assertIn('Category names in tool results are internal English keys', system)
        self.assertIn('Lifestyle: Shopping / Ostokset / Shopping', system)


if __name__ == '__main__':
    unittest.main()
