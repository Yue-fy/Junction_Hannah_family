"""Exact, account-scoped statistics for deterministic coach tools.

This module owns arithmetic over private ledger rows.  A language model may
choose a validated filter, but it must never calculate or invent these values.
"""

from datetime import date
from decimal import Decimal

from .classification import ROLES, TRANSFER_TYPES
from .ledger import account_scope, fact_id, transactions
from .money import rounded


_FILTERS = {"category", "role", "transaction_type", "merchant_id"}
_CONSUMPTION_TYPES = {"purchase", "utilities_payment", "housing_payment"}


def _period(scope, start, end):
    if not isinstance(start, str) or not isinstance(end, str):
        raise ValueError("start and end must be ISO dates")
    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(end)
    except ValueError as error:
        raise ValueError("start and end must be ISO dates") from error
    if first > last:
        raise ValueError("Reversed period")
    # The source documents complete calendar coverage.  A customer need not
    # transact on the first or last day, so boundary validation is month-based.
    if start[:7] < scope["observed_start"][:7] or end[:7] > scope["observed_end"][:7]:
        raise ValueError("Period outside observed account history")


def _filters(filters):
    if filters is None:
        return {}
    if not isinstance(filters, dict) or set(filters) - _FILTERS:
        raise ValueError("Unsupported statistics filter")
    cleaned = {}
    for key, value in filters.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Statistics filter values must be nonempty text")
        cleaned[key] = value
    if "role" in cleaned and cleaned["role"] not in ROLES:
        raise ValueError("Unknown role")
    return cleaned


def _average(total, count):
    return rounded(Decimal(total) / count) if count else None


def _largest(rows):
    outflows = [row for row in rows if row["amount_cents"] < 0]
    if not outflows:
        return None
    row = sorted(
        outflows,
        key=lambda item: (-abs(item["amount_cents"]), item["date"], item["transaction_ref"]),
    )[0]
    return {
        "transaction_ref": row["transaction_ref"],
        "date": row["date"],
        "category": row["category"],
        "merchant_id": row["merchant_id"],
        "transaction_type": row["transaction_type"],
        "role": row["role"],
        "amount_cents": abs(row["amount_cents"]),
        "observed": True,
        "fact_id": row["fact_id"],
    }


def transaction_statistics(conn, customer_id, start, end, filters=None):
    """Return exact observed totals and source references for one ledger scope."""
    scope = account_scope(conn, customer_id)
    _period(scope, start, end)
    selected_filters = _filters(filters)
    rows = transactions(conn, customer_id, start, end, selected_filters)
    inflows = [row for row in rows if row["amount_cents"] > 0]
    outflows = [row for row in rows if row["amount_cents"] < 0]
    transfer_inflows = [row for row in inflows if row["transaction_type"] in TRANSFER_TYPES]
    transfer_outflows = [row for row in outflows if row["transaction_type"] in TRANSFER_TYPES]
    consumption = [
        row
        for row in outflows
        if row["transaction_type"] in _CONSUMPTION_TYPES
        and row["transaction_type"] not in TRANSFER_TYPES
    ]
    inflow_total = sum(row["amount_cents"] for row in inflows)
    outflow_total = -sum(row["amount_cents"] for row in outflows)
    consumption_total = -sum(row["amount_cents"] for row in consumption)
    refs = [row["transaction_ref"] for row in rows]
    result = {
        **scope,
        "start": start,
        "end": end,
        "filters": selected_filters,
        "available": True,
        "has_transactions": bool(rows),
        "observed": True,
        "transaction_count": len(rows),
        "inflow_count": len(inflows),
        "outflow_count": len(outflows),
        "consumption_count": len(consumption),
        "inflow_total_cents": inflow_total,
        "outflow_total_cents": outflow_total,
        "net_cents": sum(row["amount_cents"] for row in rows),
        "consumption_cents": consumption_total,
        "transfer_inflow_cents": sum(row["amount_cents"] for row in transfer_inflows),
        "transfer_outflow_cents": -sum(row["amount_cents"] for row in transfer_outflows),
        "average_outflow_cents": _average(outflow_total, len(outflows)),
        "average_consumption_cents": _average(consumption_total, len(consumption)),
        "largest_outflow": _largest(rows),
        "transaction_refs": refs,
        "limitations": [
            "Totals use only the selected account rows, dates, and exact filters",
            "Investment deposits, withdrawals, and salary sweeps remain transfers and never count as consumption",
        ],
    }
    result["fact_id"] = fact_id(
        "transaction-statistics", customer_id, start, end, selected_filters, refs
    )
    return result


def compare_transaction_statistics(
    conn,
    customer_id,
    current_start,
    current_end,
    comparison_start,
    comparison_end,
    filters=None,
):
    """Compare two explicit observed periods using the same exact filters."""
    current = transaction_statistics(
        conn, customer_id, current_start, current_end, filters=filters
    )
    comparison = transaction_statistics(
        conn, customer_id, comparison_start, comparison_end, filters=filters
    )
    current_average = current["average_outflow_cents"]
    comparison_average = comparison["average_outflow_cents"]
    average_delta = (
        current_average - comparison_average
        if current_average is not None and comparison_average is not None
        else None
    )
    result = {
        "customer_id": current["customer_id"],
        "account_id": current["account_id"],
        "filters": current["filters"],
        "current": current,
        "comparison": comparison,
        "outflow_delta_cents": current["outflow_total_cents"] - comparison["outflow_total_cents"],
        "consumption_delta_cents": current["consumption_cents"] - comparison["consumption_cents"],
        "net_delta_cents": current["net_cents"] - comparison["net_cents"],
        "transaction_count_delta": current["transaction_count"] - comparison["transaction_count"],
        "average_outflow_delta_cents": average_delta,
        "current_fact_id": current["fact_id"],
        "comparison_fact_id": comparison["fact_id"],
        "transaction_refs": current["transaction_refs"] + comparison["transaction_refs"],
        "available": True,
        "observed": True,
    }
    result["fact_id"] = fact_id(
        "transaction-statistics-comparison", current["fact_id"], comparison["fact_id"]
    )
    return result
