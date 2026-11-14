"""Read-only, evidence-bearing financing history for optional customer goals.

The challenge data records past mortgage application events.  It does not
contain a vehicle-loan history, a current credit decision, or enough semantics
to reproduce S-Pankki underwriting.  This module therefore exposes only the
recorded synthetic facts and makes absence explicit.
"""

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .ledger import fact_id
from .money import euros_to_cents, rounded


_GOAL_TYPES = {"home", "vehicle", "custom"}
_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_SAS_TIMESTAMP = re.compile(
    r"^(\d{2})([A-Z]{3})(\d{2}):(\d{2}):(\d{2}):(\d{2})$",
    re.IGNORECASE,
)
_LIMITATIONS = [
    "Historical synthetic mortgage application context only; not a current affordability assessment.",
    "A recorded decision is not an approval prediction, loan offer, or guarantee.",
    "No financing product or amount is recommended.",
    "Fees and taxes appear only when an event recorded them; missing costs are not inferred.",
]


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _decode(value, label):
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid {label} source JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"Invalid {label} source object")
    return decoded


def _optional_cents(value):
    value = _clean(value)
    return euros_to_cents(value) if value is not None else None


def _optional_basis_points(value):
    value = _clean(value)
    if value is None:
        return None
    try:
        ratio = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid loan-to-value source value") from error
    if not ratio.is_finite():
        raise ValueError("Invalid loan-to-value source value")
    return rounded(ratio * 10_000)


def _timestamp(value):
    value = _clean(value)
    if value is None:
        return None
    match = _SAS_TIMESTAMP.fullmatch(value)
    if not match:
        raise ValueError("Invalid mortgage event timestamp")
    day, month_name, year, hour, minute, second = match.groups()
    month = _MONTHS.get(month_name.upper())
    if month is None:
        raise ValueError("Invalid mortgage event month")
    try:
        parsed = datetime(
            2000 + int(year),
            month,
            int(day),
            int(hour),
            int(minute),
            int(second),
        )
    except ValueError as error:
        raise ValueError("Invalid mortgage event timestamp") from error
    return parsed.isoformat(timespec="seconds")


def _unavailable(customer_id, goal_type, reason):
    return {
        "customer_id": customer_id,
        "goal_type": goal_type,
        "available": False,
        "reason": reason,
        "events": [],
        "event_refs": [],
        "recorded_fees": [],
        "recorded_fees_total_cents": 0,
        "recorded_transfer_tax_cents": 0,
        "historical_context_only": True,
        "limitations": list(_LIMITATIONS),
        "fact_id": fact_id("financing-history-unavailable", customer_id, goal_type, reason),
    }


def _event(row):
    raw = _decode(row["raw_json"], "mortgage event")
    source_timestamp = _clean(raw.get("timestamp")) or _clean(row["timestamp"])
    event_type = _clean(row["event_type"]) or _clean(raw.get("event_type"))
    if event_type is None:
        raise ValueError("Mortgage event type is missing")
    return {
        "event_ref": row["event_ref"],
        "timestamp": _timestamp(source_timestamp),
        "source_timestamp": source_timestamp,
        "event_type": event_type,
        "property_id": _clean(raw.get("property_id")),
        "property_type": _clean(raw.get("property_type")),
        "property_price_cents": _optional_cents(raw.get("property_price_estimate")),
        "requested_loan_cents": _optional_cents(raw.get("loan_amount")),
        "equity_cents": _optional_cents(raw.get("equity_amount")),
        "collateral_type": _clean(raw.get("collateral_type")),
        "collateral_value_cents": _optional_cents(raw.get("collateral_value")),
        "collateral_status": _clean(raw.get("collateral_status")),
        "expense_type": _clean(raw.get("expense_type")),
        "expense_amount_cents": _optional_cents(raw.get("expense_amount")),
        "decision": _clean(raw.get("decision")),
        "rejection_reason": _clean(raw.get("rejection_reason")),
        "description": _clean(raw.get("note")),
        "observed": True,
    }


def financing_context(conn, customer_id, goal_type="home"):
    """Return recorded financing history without deriving eligibility or advice."""
    if not isinstance(customer_id, str) or not conn.execute(
        "SELECT 1 FROM customers WHERE customer_id=?", (customer_id,)
    ).fetchone():
        raise ValueError("Unknown customer")
    if goal_type not in _GOAL_TYPES:
        raise ValueError("goal_type must be home, vehicle, or custom")
    if goal_type != "home":
        return _unavailable(
            customer_id, goal_type, "no_financing_history_for_goal_type"
        )

    final_row = conn.execute(
        "SELECT mortgage_customer_id,raw_json FROM mortgage_final WHERE customer_id=?",
        (customer_id,),
    ).fetchone()
    if final_row is None:
        return _unavailable(customer_id, goal_type, "no_linked_mortgage_history")

    final = _decode(final_row["raw_json"], "mortgage final")
    mortgage_customer_id = final_row["mortgage_customer_id"]
    events = [
        _event(row)
        for row in conn.execute(
            "SELECT event_ref,timestamp,event_type,raw_json "
            "FROM mortgage_events WHERE mortgage_customer_id=?",
            (mortgage_customer_id,),
        )
    ]
    events.sort(
        key=lambda event: (
            event["timestamp"] is None,
            event["timestamp"] or "",
            event["event_ref"],
        )
    )
    event_refs = [event["event_ref"] for event in events]
    fees = [
        {
            "event_ref": event["event_ref"],
            "timestamp": event["timestamp"],
            "expense_type": event["expense_type"],
            "amount_cents": event["expense_amount_cents"],
            "observed": True,
        }
        for event in events
        if event["event_type"] == "expense_recorded"
        and event["expense_type"] is not None
        and event["expense_amount_cents"] is not None
    ]
    recorded_fees_total = sum(fee["amount_cents"] for fee in fees)
    transfer_tax = sum(
        fee["amount_cents"]
        for fee in fees
        if fee["expense_type"] == "transfer_tax"
    )

    result = {
        "customer_id": customer_id,
        "goal_type": goal_type,
        "mortgage_customer_id": mortgage_customer_id,
        "available": True,
        "observed": True,
        "historical_context_only": True,
        "property_price_cents": _optional_cents(
            final.get("final_property_price_eur")
        ),
        "requested_loan_cents": _optional_cents(
            final.get("final_requested_loan_eur")
        ),
        "equity_cents": _optional_cents(final.get("final_equity_amount_eur")),
        "collateral_value_cents": _optional_cents(
            final.get("final_collateral_value_eur")
        ),
        "loan_to_value_basis_points": _optional_basis_points(
            final.get("lfinal_loan_to_value")
        ),
        "recorded_outcome": {
            "decision": _clean(final.get("final_decision")),
            "rejection_reason": _clean(final.get("rejection_reason")),
        },
        "events": events,
        "event_refs": event_refs,
        "recorded_fees": fees,
        "recorded_fees_total_cents": recorded_fees_total,
        "recorded_transfer_tax_cents": transfer_tax,
        "unpriced_expense_event_refs": [
            event["event_ref"]
            for event in events
            if event["event_type"] == "expense_recorded"
            and event["expense_amount_cents"] is None
        ],
        "required_income_comparability": {
            "available": False,
            "reason": (
                "The required_monthly_income_eur field has undocumented "
                "gross, net, and household semantics and is excluded from calculations."
            ),
        },
        "limitations": list(_LIMITATIONS),
    }
    result["fact_id"] = fact_id(
        "financing-history",
        customer_id,
        mortgage_customer_id,
        result["property_price_cents"],
        result["requested_loan_cents"],
        result["equity_cents"],
        result["collateral_value_cents"],
        result["recorded_outcome"],
        event_refs,
    )
    return result
