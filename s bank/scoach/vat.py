"""Transparent estimates of VAT already included in observed purchase prices.

This is a financial-literacy lens, not a tax-liability calculator. Rates are
selected from the transaction date and an explicit MCC-first mapping. Unknown
items remain uncovered instead of receiving an invented rate.
"""

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .classification import TRANSFER_TYPES
from .ledger import account_scope, fact_id, transactions
from .money import rounded


_CONSUMPTION_TYPES = {"purchase", "utilities_payment", "housing_payment"}

VAT_METHOD_VERSION = "gross-inside-vat-per-row-half-up-v2"
VAT_RATE_MAP_VERSION = "fi-2024-10-through-2026-mcc-category-v2"

_MCC_BANDS = {
    "5411": "food",
    "5422": "food",
    "5451": "food",
    "5499": "food",
    "5812": "food",
    "5814": "food",
    "5813": "general",
    "4111": "reduced",
    "4121": "reduced",
    "4511": "reduced",
    "5912": "reduced",
    "7011": "reduced",
    "7832": "reduced",
    "7922": "reduced",
    "8011": "exempt",
    "8021": "exempt",
    "8099": "exempt",
    "5541": "general",
    "5542": "general",
    "7523": "general",
    "7512": "general",
    "5200": "general",
    "5251": "general",
    "5651": "general",
    "5691": "general",
    "5712": "general",
    "5732": "general",
    "5734": "general",
    "5941": "general",
    "5942": "reduced",
    "5945": "general",
    "5999": "general",
}

# These recreation codes can cover services with different Finnish VAT
# treatment. The general band preserves the documented demo estimate, but the
# row is explicitly labelled as broad rather than presented as a precise map.
_BROAD_MCC_BANDS = {
    "7991": "general",
    "7996": "general",
    "7999": "general",
}

_CATEGORY_BANDS = {
    "groceries": "food",
    "restaurants": "food",
    "transportation": "reduced",
    "travel": "reduced",
    "housing": "exempt",
    "health": "exempt",
    "utilities": "general",
    "home & tech": "general",
    "lifestyle": "general",
    "entertainment": "general",
    "newspapers": "newspapers",
}

_AMBIGUOUS_CATEGORIES = {"transportation", "travel", "health", "entertainment"}
_BROAD_CATEGORY_FALLBACKS = {"groceries", "restaurants"}

_LIMITATIONS = [
    "All VAT amounts are estimated from the gross transaction price, date, and an MCC-first category mapping",
    "Grocery and restaurant purchases may contain goods with another rate; alcohol served in restaurants remains at the general rate",
    "Broad estimates are labelled per row; ambiguous transport, travel, health, or entertainment rows remain uncovered unless a supported MCC supplies a band",
    "Excise duties on products such as fuel, alcohol, and tobacco are not included",
    "This lens does not calculate a personal tax liability, deduction, or filing position",
]


def _mcc(value):
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized.endswith(".0") and normalized[:-2].isdigit():
        normalized = normalized[:-2]
    return normalized or None


def _rate_basis_points(day, band):
    when = date.fromisoformat(day)
    if when < date(2024, 10, 1):
        raise ValueError("VAT lens supports the dataset period from 2024-10-01")
    if band == "exempt":
        return 0
    if band == "general":
        return 2550
    if band == "newspapers":
        return 1000
    if band == "food":
        return 1350 if when >= date(2026, 1, 1) else 1400
    if band == "reduced":
        if when >= date(2026, 1, 1):
            return 1350
        if when >= date(2025, 1, 1):
            return 1400
        return 1000
    raise ValueError("Unknown VAT rate band")


def _inside_vat(gross_cents, rate_basis_points):
    if rate_basis_points == 0:
        return 0
    value = Decimal(gross_cents * rate_basis_points) / Decimal(10_000 + rate_basis_points)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _rate_label(rate_basis_points):
    rate = Decimal(rate_basis_points) / 100
    return f"{rate.normalize()}%"


def _select_band(mcc, category, category_key):
    if mcc in _MCC_BANDS:
        return (
            _MCC_BANDS[mcc],
            {"kind": "mcc", "value": mcc},
            "direct_mcc",
            f"Supported MCC {mcc} selected the VAT band",
        )
    if mcc in _BROAD_MCC_BANDS:
        return (
            _BROAD_MCC_BANDS[mcc],
            {"kind": "mcc", "value": mcc},
            "broad_mcc_estimate",
            f"Ambiguous recreation MCC {mcc} uses the documented broad estimate",
        )
    if category_key in _AMBIGUOUS_CATEGORIES:
        detail = "missing MCC" if mcc is None else f"unsupported MCC {mcc}"
        return (
            "unknown",
            {"kind": "unmapped", "value": mcc or category or "unknown"},
            "unmapped",
            f"Ambiguous {category or 'transaction'} rate with {detail}; no rate was assumed",
        )
    if category_key in _CATEGORY_BANDS:
        if mcc is not None or category_key in _BROAD_CATEGORY_FALLBACKS:
            quality = "broad_category_estimate"
            note = f"Category {category} supplied a broad estimate because MCC {mcc or 'was missing'} did not select a precise band"
        else:
            quality = "category_fallback"
            note = f"Category {category} supplied the documented fallback band"
        return (
            _CATEGORY_BANDS[category_key],
            {"kind": "category", "value": category},
            quality,
            note,
        )
    return (
        "unknown",
        {"kind": "unmapped", "value": mcc or category or "unknown"},
        "unmapped",
        "No supported MCC or category VAT mapping was available",
    )


def estimate_transaction_vat(row):
    """Estimate VAT inside one observed outflow, or return ``None`` if not spending."""
    kind = row.get("transaction_type")
    amount = row.get("amount_cents")
    if (
        type(amount) is not int
        or amount >= 0
        or kind in TRANSFER_TYPES
        or kind not in _CONSUMPTION_TYPES
    ):
        return None
    try:
        date.fromisoformat(row.get("date", ""))
    except (TypeError, ValueError) as error:
        raise ValueError("Transaction date must be an ISO date") from error

    mcc = _mcc(row.get("mcc_code"))
    category = str(row.get("category", "")).strip()
    band, source, mapping_quality, mapping_note = _select_band(mcc, category, category.casefold())

    gross = abs(amount)
    rate = None if band == "unknown" else _rate_basis_points(row["date"], band)
    vat = None if rate is None else _inside_vat(gross, rate)
    return {
        "transaction_ref": row.get("transaction_ref"),
        "date": row["date"],
        "category": category,
        "merchant_id": row.get("merchant_id"),
        "mcc_code": mcc,
        "gross_cents": gross,
        "estimated_vat_cents": vat,
        "rate_basis_points": rate,
        "rate_display": None if rate is None else _rate_label(rate),
        "rate_band": band,
        "rate_source": source,
        "mapping_quality": mapping_quality,
        "mapping_note": mapping_note,
        "method_version": VAT_METHOD_VERSION,
        "rate_map_version": VAT_RATE_MAP_VERSION,
        "estimated": True,
        "observed": True,
        "source_observed": True,
        "source_status": "observed",
        "value_status": "estimated",
        "scenario": False,
    }


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
    observed_first = date.fromisoformat(scope["observed_start"])
    observed_last = date.fromisoformat(scope["observed_end"])
    complete_month = (
        first.year == last.year
        and first.month == last.month
        and first.day == 1
        and last.day == calendar.monthrange(last.year, last.month)[1]
    )
    outside = (
        first.strftime("%Y-%m") < observed_first.strftime("%Y-%m")
        or last.strftime("%Y-%m") > observed_last.strftime("%Y-%m")
    ) if complete_month else first < observed_first or last > observed_last
    if outside:
        raise ValueError("Period outside observed account history")


def vat_lens(conn, customer_id, start, end):
    """Return a per-transaction and period VAT estimate with coverage evidence."""
    scope = account_scope(conn, customer_id)
    _period(scope, start, end)
    estimates = []
    for row in transactions(conn, customer_id, start, end):
        estimate = estimate_transaction_vat(row)
        if estimate is not None:
            estimates.append(estimate)

    covered = [item for item in estimates if item["estimated_vat_cents"] is not None]
    gross = sum(item["gross_cents"] for item in estimates)
    covered_gross = sum(item["gross_cents"] for item in covered)
    by_rate = {}
    for item in covered:
        key = (item["rate_basis_points"], item["rate_band"])
        aggregate = by_rate.setdefault(
            key,
            {
                "rate_basis_points": item["rate_basis_points"],
                "rate_display": item["rate_display"],
                "rate_band": item["rate_band"],
                "gross_cents": 0,
                "estimated_vat_cents": 0,
                "transaction_count": 0,
            },
        )
        aggregate["gross_cents"] += item["gross_cents"]
        aggregate["estimated_vat_cents"] += item["estimated_vat_cents"]
        aggregate["transaction_count"] += 1

    refs = [item["transaction_ref"] for item in estimates if item["transaction_ref"]]
    result = {
        **scope,
        "start": start,
        "end": end,
        "gross_spending_cents": gross,
        "covered_spending_cents": covered_gross,
        "uncovered_spending_cents": gross - covered_gross,
        "coverage_basis_points": rounded(Decimal(covered_gross * 10_000) / gross) if gross else 0,
        "estimated_vat_cents": sum(item["estimated_vat_cents"] for item in covered),
        "transactions": estimates,
        "by_rate": [by_rate[key] for key in sorted(by_rate)],
        "transaction_refs": refs,
        "method_version": VAT_METHOD_VERSION,
        "rate_map_version": VAT_RATE_MAP_VERSION,
        "estimated": True,
        "observed": True,
        "source_observed": True,
        "source_status": "observed",
        "value_status": "estimated",
        "scenario": False,
        "method": "VAT inside gross price = gross × rate / (1 + rate), rounded half up to cents per transaction",
        "limitations": list(_LIMITATIONS),
    }
    evidence = [
        (
            item["transaction_ref"],
            item["date"],
            item["gross_cents"],
            item["estimated_vat_cents"],
            item["rate_basis_points"],
            item["rate_band"],
            item["mapping_quality"],
        )
        for item in estimates
    ]
    result["fact_id"] = fact_id(
        "vat-lens",
        VAT_METHOD_VERSION,
        VAT_RATE_MAP_VERSION,
        customer_id,
        start,
        end,
        evidence,
    )
    return result
