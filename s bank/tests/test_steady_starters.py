import unittest
from scoach.catalogue import catalogue, QUESTIONS

SAVING = {'room.save_now', 'room.save_more', 'room.cut', 'goals.new', 'spend.spender', 'me.peers'}


class SteadyStarterTests(unittest.TestCase):
    def test_steady_mode_starters_never_invite_saving_or_cutting_back(self):
        for locale in ('en', 'fi', 'sv'):
            starters = catalogue(locale, steady=True)['starters']
            self.assertEqual(len(starters), 6)
            self.assertFalse(SAVING & set(starters), starters)
            self.assertTrue(all(q in QUESTIONS for q in starters))

    def test_normal_starters_keep_the_briefs_four_questions(self):
        starters = catalogue('en')['starters']
        for q in ('money.where', 'spend.spender', 'room.week', 'room.save_more'):
            self.assertIn(q, starters)


if __name__ == '__main__':
    unittest.main()
