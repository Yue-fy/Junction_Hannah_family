import unittest
from scoach.classification import classify

class ClassificationTests(unittest.TestCase):
    def test_roles_preserve_transfers_unknown_and_user_labels(self):
        for kind in ('investment_deposit','investment_withdrawal','salary_sweep'):
            self.assertEqual(classify({'transaction_type':kind,'category':'Other'})['role'],'saving_or_transfer')
        self.assertEqual(classify({'transaction_type':'salary','category':'Salary'})['role'],'income')
        self.assertEqual(classify({'transaction_type':'purchase','category':'Groceries'})['literacy_label'],'irregular essentials')
        self.assertEqual(classify({'transaction_type':'mystery','category':'Unknown'})['role'],'needs_review')
        c=classify({'transaction_type':'purchase','category':'Restaurants'}, {'role':'fixed_obligation','label':'Tax','provenance':'user'})
        self.assertEqual(c['literacy_label'],'regular essentials'); self.assertEqual(c['source'],'user')

    def test_transfer_cannot_be_misrepresented_as_consumption_by_role_override(self):
        result=classify({'transaction_type':'investment_deposit','category':'Invest Deposit'}, {'role':'discretionary','provenance':'user'})
        self.assertEqual(result['role'],'saving_or_transfer')
