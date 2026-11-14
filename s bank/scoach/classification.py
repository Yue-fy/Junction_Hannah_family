"""Source-seeded roles, with explicit user corrections kept separate."""
ROLES={'income','fixed_obligation','flexible_essential','discretionary','saving_or_transfer','needs_review'}
LABELS={'fixed_obligation':'regular essentials','flexible_essential':'irregular essentials','discretionary':'everyday discretionary','needs_review':'needs review','income':'income','saving_or_transfer':'saving/transfers'}
TRANSFER_TYPES={'investment_deposit','investment_withdrawal','salary_sweep'}
COMMITTED_TYPES={'investment_deposit','salary_sweep'}


def classify(row, override=None):
    kind=row.get('transaction_type'); category=row.get('category','')
    if kind in TRANSFER_TYPES: role='saving_or_transfer'
    elif kind in ('salary','other_income'): role='income'
    elif kind in ('housing_payment','utilities_payment'): role='fixed_obligation'
    elif category in ('Housing','Utilities','Groceries','Transportation'): role='fixed_obligation'
    elif category in ('Health','Home & Tech'): role='flexible_essential'
    elif category in ('Restaurants','Entertainment','Lifestyle','Travel'): role='discretionary'
    else: role='needs_review'
    source='dataset'
    if override and kind not in TRANSFER_TYPES:
        role=override['role']; source=override['provenance']
    return {'role':role,'literacy_label':LABELS[role],'source':source,'user_label':override.get('label') if override else None}
