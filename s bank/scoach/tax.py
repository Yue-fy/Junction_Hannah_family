"""Explicit tax evidence and user-declared planning scenarios.

No tax category, liability, rate, filing rule, or legal conclusion is inferred.
"""

from datetime import date

from .financing import financing_context
from .ledger import account_scope, fact_id, transactions


_EXPLICIT_TRANSACTION_CATEGORIES = {
    "tax",
    "taxes",
    "income tax",
    "property tax",
    "transfer tax",
    "transfer_tax",
}
_LIMITATIONS = [
    "Only transaction categories or mortgage expense fields that explicitly name a tax are included; taxes are not inferred",
    "Missing records do not mean that no tax was paid",
    "This evidence is not tax advice and does not establish a tax liability or filing position",
]


def _period(scope, start, end):
    start = start or scope["observed_start"]
    end = end or scope["observed_end"]
    if not isinstance(start, str) or not isinstance(end, str):
        raise ValueError("start and end must be ISO dates")
    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(end)
    except ValueError as error:
        raise ValueError("start and end must be ISO dates") from error
    if first > last:
        raise ValueError("Reversed period")
    if start[:7] < scope["observed_start"][:7] or end[:7] > scope["observed_end"][:7]:
        raise ValueError("Period outside observed account history")
    return start, end


def observed_tax_evidence(conn, customer_id, start=None, end=None):
    """Return observed records only when a source field explicitly names tax."""
    scope = account_scope(conn, customer_id)
    start, end = _period(scope, start, end)
    tax_rows = [
        row
        for row in transactions(conn, customer_id, start, end)
        if row["category"].strip().casefold() in _EXPLICIT_TRANSACTION_CATEGORIES
    ]
    records = []
    for row in tax_rows:
        records.append(
            {
                "source": "transaction",
                "source_ref": row["transaction_ref"],
                "date": row["date"],
                "label": row["category"],
                "paid_cents": abs(row["amount_cents"]) if row["amount_cents"] < 0 else 0,
                "refund_cents": row["amount_cents"] if row["amount_cents"] > 0 else 0,
                "observed": True,
            }
        )

    financing = financing_context(conn, customer_id, goal_type="home")
    if financing["available"]:
        event_dates = {
            event["event_ref"]: event["timestamp"][:10] if event["timestamp"] else None
            for event in financing["events"]
        }
        for fee in financing["recorded_fees"]:
            event_date = event_dates.get(fee["event_ref"])
            if (
                fee["expense_type"] == "transfer_tax"
                and event_date is not None
                and start <= event_date <= end
            ):
                records.append(
                    {
                        "source": "mortgage_event",
                        "source_ref": fee["event_ref"],
                        "date": event_date,
                        "label": "transfer_tax",
                        "paid_cents": fee["amount_cents"],
                        "refund_cents": 0,
                        "observed": True,
                    }
                )
    records.sort(key=lambda item: (item["date"], item["source"], item["source_ref"]))
    transaction_refs = [
        item["source_ref"] for item in records if item["source"] == "transaction"
    ]
    event_refs = [
        item["source_ref"] for item in records if item["source"] == "mortgage_event"
    ]
    if not records:
        return {
            **scope,
            "start": start,
            "end": end,
            "available": False,
            "reason": "no_explicit_tax_records",
            "observed": True,
            "observed_tax_paid_cents": None,
            "observed_tax_refund_cents": None,
            "observed_net_tax_cents": None,
            "records": [],
            "transaction_refs": [],
            "mortgage_event_refs": [],
            "limitations": list(_LIMITATIONS),
            "fact_id": fact_id("observed-tax-unavailable", customer_id, start, end),
        }
    paid = sum(item["paid_cents"] for item in records)
    refunds = sum(item["refund_cents"] for item in records)
    result = {
        **scope,
        "start": start,
        "end": end,
        "available": True,
        "observed": True,
        "observed_tax_paid_cents": paid,
        "observed_tax_refund_cents": refunds,
        "observed_net_tax_cents": paid - refunds,
        "records": records,
        "transaction_refs": transaction_refs,
        "mortgage_event_refs": event_refs,
        "limitations": list(_LIMITATIONS),
    }
    result["fact_id"] = fact_id(
        "observed-tax", customer_id, start, end, transaction_refs, event_refs
    )
    return result


def _cents(name, value, *, positive=False, optional=False, signed=False):
    if optional and value is None:
        return None
    if type(value) is not int or (positive and value <= 0) or (not positive and not signed and value < 0):
        qualifier = "positive " if positive else ("signed " if signed else "nonnegative ")
        raise ValueError(f"{name} must be {qualifier}integer cents")
    return value


def tax_planning_scenario(
    amount_cents,
    due_date,
    reference_date,
    already_set_aside_cents=0,
    current_balance_cents=None,
    reserve_floor_cents=0,
    set_aside_location="inside_current_balance",
    label="Tax planning amount",
):
    """Model only the amount and date explicitly supplied by the user."""
    amount_cents = _cents("amount_cents", amount_cents, positive=True)
    already_set_aside_cents = _cents("already_set_aside_cents", already_set_aside_cents)
    reserve_floor_cents = _cents("reserve_floor_cents", reserve_floor_cents)
    current_balance_cents = _cents(
        "current_balance_cents", current_balance_cents, optional=True, signed=True
    )
    if not isinstance(label, str) or not label.strip():
        raise ValueError("label must be nonempty text")
    if set_aside_location not in {
        "inside_current_balance",
        "outside_current_balance",
    }:
        raise ValueError(
            "set_aside_location must be inside_current_balance or outside_current_balance"
        )
    if not isinstance(due_date, str) or not isinstance(reference_date, str):
        raise ValueError("due_date and reference_date must be ISO dates")
    try:
        due = date.fromisoformat(due_date)
        reference = date.fromisoformat(reference_date)
    except ValueError as error:
        raise ValueError("due_date and reference_date must be ISO dates") from error
    if due <= reference:
        raise ValueError("due_date must be after reference_date")
    remaining = max(amount_cents - already_set_aside_cents, 0)
    periods = max(1, (due.year - reference.year) * 12 + due.month - reference.month)
    monthly = (remaining + periods - 1) // periods if remaining else 0
    protected_from_balance = (
        amount_cents
        if set_aside_location == "inside_current_balance"
        else remaining
    )
    available_above = (
        max(current_balance_cents - reserve_floor_cents, 0)
        if current_balance_cents is not None
        else None
    )
    result = {
        "label": label.strip(),
        "amount_cents": amount_cents,
        "already_set_aside_cents": already_set_aside_cents,
        "set_aside_location": set_aside_location,
        "remaining_cents": remaining,
        "due_date": due.isoformat(),
        "reference_date": reference.isoformat(),
        "remaining_monthly_periods": periods,
        "required_monthly_set_aside_cents": monthly,
        "current_balance_cents": current_balance_cents,
        "reserve_floor_cents": reserve_floor_cents,
        "protected_from_current_balance_cents": protected_from_balance,
        "available_above_reserve_cents": available_above,
        "available_after_full_set_aside_cents": (
            max(available_above - protected_from_balance, 0)
            if available_above is not None
            else None
        ),
        "upfront_funding_gap_cents": (
            max(protected_from_balance - available_above, 0)
            if available_above is not None
            else None
        ),
        "source": "user_declared",
        "scenario": True,
        "observed": False,
        "not_tax_advice": True,
        "persistence": "not_saved",
        "assumptions": [
            "The amount and due date are supplied by the user",
            (
                "The amount already set aside is included in current_balance_cents, so the full declared tax amount remains protected from that balance"
                if set_aside_location == "inside_current_balance"
                else "The amount already set aside is held outside current_balance_cents, so only the remaining tax amount is protected from that balance"
            ),
            "No tax rate, liability, deduction, filing rule, or future income is inferred",
            "Monthly set-asides divide the remaining amount across calendar-month periods and round up to the next cent",
        ],
        "limitations": [
            "This planning scenario is not tax advice",
            "It does not calculate tax liability, eligibility, deductions, or filing requirements",
            "It is not saved until a future confirmed-obligation workflow is implemented",
        ],
    }
    result["scenario_id"] = fact_id(
        "tax-planning-scenario",
        amount_cents,
        due.isoformat(),
        reference.isoformat(),
        already_set_aside_cents,
        current_balance_cents,
        reserve_floor_cents,
        set_aside_location,
        result["label"],
    )
    return result
