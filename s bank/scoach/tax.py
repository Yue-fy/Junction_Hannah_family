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


# ---------------------------------------------------------------------------
# WP-M: income tax tracking from customer-entered tax-card and decision data.
#
# Every rate, income limit and amount below comes from the `tax` dict the
# customer entered (their tax card or tax decision). No rate, limit or payroll
# contribution share is written into this module. Dates come from the
# customer's tax decision first and from the data/tax calendar file second.
# ---------------------------------------------------------------------------

import json
from datetime import timedelta
from pathlib import Path

from .ledger import month_bounds
from .money import cents_to_euros
from .vat import vat_lens

TAX_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "tax"

BASIS_POINTS_PER_WHOLE = 10_000  # unit conversion only: basis points to a fraction
MONTHS_PER_YEAR = 12

MISSING_WITHHOLDING_REASON = (
    "Your account shows salary after tax, so I need your gross salary from a "
    "payslip and your tax-card rate."
)
TAX_FOOTER = (
    "Estimate from what you entered. Your tax decision in MyTax is the official source."
)
CHECK_MYTAX_NOTE = "Check MyTax for your exact dates."

# A gap between expected and observed net pay above this many cents per salary
# month is called large. It is a money threshold for a note, not a tax rate.
LARGE_NET_GAP_CENTS_PER_MONTH = 5_000
# Refund matching: amount tolerance (one euro) and the window around the
# expected payment date.
REFUND_MATCH_TOLERANCE_CENTS = 100
REFUND_WINDOW_DAYS_BEFORE = 7
REFUND_WINDOW_DAYS_AFTER = 21
# A refund or back-tax decision stays the active stage until this many days
# after its last payment date.
DECISION_STAGE_GRACE_DAYS = 14

TAX_STAGES = (
    "return_coming",
    "check_return",
    "decision_pending",
    "refund_expected",
    "back_tax_due",
    "year_end",
)
_STAGE_LABELS = {
    "return_coming": "Your pre-completed tax return is coming",
    "check_return": "Time to check your tax return",
    "decision_pending": "Waiting for your tax decision",
    "refund_expected": "Tax refund expected",
    "back_tax_due": "Back taxes to pay",
    "year_end": "End of the tax year",
}
_INT_FIELDS = (
    "tax_year",
    "base_rate_bp",
    "additional_rate_bp",
    "income_limit_cents",
    "gross_monthly_cents",
    "gross_ytd_cents",
    "decision_amount_cents",
    "already_set_aside_cents",
)
_DECISION_RESULTS = {"refund", "back_tax", "none"}
_AI_HIDDEN_KEYS = {"base_rate_bp", "additional_rate_bp"}


def _euro(cents):
    if cents is None:
        return None
    sign = "-" if cents < 0 else ""
    return sign + "€" + cents_to_euros(abs(cents))


def _clean_tax(tax):
    """Validate the customer's tax entry; return a dict with every known key."""
    if tax is None:
        tax = {}
    if not isinstance(tax, dict):
        raise ValueError("tax must be a dict or None")
    clean = {}
    for key in _INT_FIELDS:
        value = tax.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(key + " must be a nonnegative integer")
        clean[key] = value
    month = tax.get("assessment_end_month")
    if month is not None:
        try:
            month_bounds(month)
        except (TypeError, ValueError) as error:
            raise ValueError("assessment_end_month must be YYYY-MM") from error
    clean["assessment_end_month"] = month
    result = tax.get("decision_result")
    if result is not None and result not in _DECISION_RESULTS:
        raise ValueError("decision_result must be refund, back_tax or none")
    clean["decision_result"] = result
    dates = tax.get("decision_due_dates") or []
    if not isinstance(dates, (list, tuple)):
        raise ValueError("decision_due_dates must be a list of ISO dates")
    parsed = []
    for value in dates:
        try:
            parsed.append(date.fromisoformat(value).isoformat())
        except (TypeError, ValueError) as error:
            raise ValueError("decision_due_dates must be a list of ISO dates") from error
    clean["decision_due_dates"] = sorted(parsed)
    return clean


def _as_of(conn, customer_id, as_of):
    scope = account_scope(conn, customer_id)
    if as_of is None:
        return scope, date.fromisoformat(scope["observed_end"])
    try:
        return scope, date.fromisoformat(as_of)
    except (TypeError, ValueError) as error:
        raise ValueError("as_of must be an ISO date") from error


def _apply_rate(amount_cents, rate_bp):
    """amount × rate in basis points, rounded half up to whole cents."""
    return (amount_cents * rate_bp + BASIS_POINTS_PER_WHOLE // 2) // BASIS_POINTS_PER_WHOLE


def _withheld(gross_cents, base_rate_bp, additional_rate_bp, income_limit_cents):
    if additional_rate_bp is not None and income_limit_cents is not None and gross_cents > income_limit_cents:
        below = _apply_rate(income_limit_cents, base_rate_bp)
        above = _apply_rate(gross_cents - income_limit_cents, additional_rate_bp)
        return below + above, True
    return _apply_rate(gross_cents, base_rate_bp), False


def load_tax_calendar(year=2026):
    """Load the Finnish tax-cycle calendar for a calendar year.

    Args:
        year: calendar year (int) whose file data/tax/fi_tax_calendar_<year>.json
            should be read.
    Returns:
        The calendar dict (keys: calendar_year, tax_year, retrieved_at,
        verified, return_check_due_dates [ISO], revised_decision_by (ISO),
        refund_dates_by_assessment_end_month {YYYY-MM: ISO},
        back_tax_instalments_by_assessment_end_month {YYYY-MM: [ISO, ISO]},
        back_tax_two_instalments_above_cents, back_tax_not_collected_below_cents,
        sources [{title, url, covers}]), or None if no file exists for that year.
    """
    if type(year) is not int:
        raise ValueError("year must be an integer")
    path = TAX_DATA_DIR / ("fi_tax_calendar_%d.json" % year)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _salary_rows(conn, customer_id, start, end):
    return [
        row
        for row in transactions(conn, customer_id, start, end)
        if row["transaction_type"] == "salary" and row["amount_cents"] > 0
    ]


def withholding_estimate(conn, customer_id, as_of, tax):
    """Estimate income tax withheld this year from the customer's own tax-card data.

    Args:
        conn: sqlite connection to the ledger.
        customer_id: customer id.
        as_of: ISO date (str) or None for the last observed ledger date.
        tax: the customer's `tax` profile dict (may be None or partial). Uses
            tax_year (defaults to as_of's year), base_rate_bp, additional_rate_bp,
            income_limit_cents, gross_monthly_cents, gross_ytd_cents.
    Returns dict:
        available (bool); when False: reason (plain sentence), missing [field names].
        When True: tax_year, period {start, end}, salary_months (int, distinct
        months with a salary credit in the tax year up to as_of), salary_count,
        gross_ytd_cents, gross_ytd_source ("entered_ytd"|"monthly_x_salary_months"),
        withheld_ytd_cents, additional_rate_applied (bool), expected_net_ytd_cents,
        observed_net_salary_ytd_cents, net_gap_cents (expected net minus observed
        net), gap_is_large (bool), projected_gross_full_year_cents,
        projected_withheld_full_year_cents, projected_additional_rate_applied
        (projection fields None unless gross_monthly_cents was given),
        flow {gross_cents, withheld_cents, received_cents, text},
        inputs {base_rate_bp, additional_rate_bp, income_limit_cents,
        gross_monthly_cents, gross_ytd_cents}, notes [str], assumptions [str],
        transaction_refs [salary refs], footer, source "user_declared_and_observed".
        All amounts are integer cents; *_text/flow.text are formatted extras.
    """
    tax = _clean_tax(tax)
    scope, day = _as_of(conn, customer_id, as_of)
    year = tax["tax_year"] or day.year
    missing = []
    if tax["base_rate_bp"] is None:
        missing.append("base_rate_bp")
    if tax["gross_monthly_cents"] is None and tax["gross_ytd_cents"] is None:
        missing.append("gross_monthly_cents or gross_ytd_cents")
    if missing:
        return {
            "available": False,
            "reason": MISSING_WITHHOLDING_REASON,
            "missing": missing,
            "tax_year": year,
            "footer": TAX_FOOTER,
        }
    start = date(year, 1, 1).isoformat()
    end = min(day, date(year, 12, 31)).isoformat()
    rows = _salary_rows(conn, customer_id, start, end) if start <= end else []
    salary_months = len({row["date"][:7] for row in rows})
    observed_net = sum(row["amount_cents"] for row in rows)
    if tax["gross_ytd_cents"] is not None:
        gross_ytd = tax["gross_ytd_cents"]
        gross_source = "entered_ytd"
    else:
        gross_ytd = tax["gross_monthly_cents"] * salary_months
        gross_source = "monthly_x_salary_months"
    withheld_ytd, additional_applied = _withheld(
        gross_ytd, tax["base_rate_bp"], tax["additional_rate_bp"], tax["income_limit_cents"]
    )
    expected_net = gross_ytd - withheld_ytd
    gap = expected_net - observed_net
    gap_is_large = salary_months > 0 and abs(gap) > LARGE_NET_GAP_CENTS_PER_MONTH * salary_months
    projected_gross = projected_withheld = projected_additional = None
    assumptions = [
        "Rates, income limit and gross salary are the figures you entered from your tax card and payslip",
        "Salary months are months with a salary credit in the account during the tax year up to the as-of date",
    ]
    if tax["additional_rate_bp"] is not None and tax["income_limit_cents"] is not None:
        assumptions.append("Your base rate applies up to your income limit and your additional rate above it")
    else:
        assumptions.append("Your base rate applies to all gross salary because no additional rate and income limit were entered")
    if tax["gross_monthly_cents"] is not None:
        remaining = max(MONTHS_PER_YEAR - salary_months, 0)
        projected_gross = gross_ytd + tax["gross_monthly_cents"] * remaining
        projected_withheld, projected_additional = _withheld(
            projected_gross, tax["base_rate_bp"], tax["additional_rate_bp"], tax["income_limit_cents"]
        )
        assumptions.append(
            "The full-year projection adds your monthly gross salary for each remaining month of the year, one salary per month, with no bonuses or holiday pay"
        )
    notes = []
    if gap_is_large:
        notes.append(
            "Your received salary differs from gross minus withholding. Pension and unemployment insurance contributions and other payroll deductions are not included in this estimate."
        )
    if salary_months == 0:
        notes.append("No salary credits were found in the account for this tax year yet.")
    flow_text = "Gross ≈ %s → withheld ≈ %s → received %s" % (
        _euro(gross_ytd), _euro(withheld_ytd), _euro(observed_net)
    )
    result = {
        "available": True,
        "tax_year": year,
        "period": {"start": start, "end": end},
        "salary_months": salary_months,
        "salary_count": len(rows),
        "gross_ytd_cents": gross_ytd,
        "gross_ytd_source": gross_source,
        "withheld_ytd_cents": withheld_ytd,
        "additional_rate_applied": additional_applied,
        "expected_net_ytd_cents": expected_net,
        "observed_net_salary_ytd_cents": observed_net,
        "net_gap_cents": gap,
        "gap_is_large": gap_is_large,
        "projected_gross_full_year_cents": projected_gross,
        "projected_withheld_full_year_cents": projected_withheld,
        "projected_additional_rate_applied": projected_additional,
        "flow": {
            "gross_cents": gross_ytd,
            "withheld_cents": withheld_ytd,
            "received_cents": observed_net,
            "text": flow_text,
        },
        "inputs": {
            "base_rate_bp": tax["base_rate_bp"],
            "additional_rate_bp": tax["additional_rate_bp"],
            "income_limit_cents": tax["income_limit_cents"],
            "gross_monthly_cents": tax["gross_monthly_cents"],
            "gross_ytd_cents": tax["gross_ytd_cents"],
        },
        "notes": notes,
        "assumptions": assumptions,
        "basis": "Salary credits in the account this tax year, and the gross salary and tax-card rates you entered",
        "transaction_refs": [row["transaction_ref"] for row in rows],
        "estimated": True,
        "source": "user_declared_and_observed",
        "not_tax_advice": True,
        "footer": TAX_FOOTER,
    }
    result["fact_id"] = fact_id(
        "withholding-estimate", customer_id, end, sorted(result["inputs"].items()), result["transaction_refs"]
    )
    return result


def _calendar_for(day, calendar):
    if calendar is None:
        calendar = load_tax_calendar(day.year)
    if calendar is not None and calendar.get("calendar_year") != day.year:
        return None
    return calendar


def _refund_date(tax, calendar):
    """(ISO date or None, source) for the expected refund payment."""
    if tax["decision_due_dates"]:
        return tax["decision_due_dates"][0], "tax_decision"
    month = tax["assessment_end_month"]
    if calendar and month:
        value = calendar.get("refund_dates_by_assessment_end_month", {}).get(month)
        if value:
            return value, "calendar"
    return None, None


def _back_tax_dates(tax, calendar):
    """(list of ISO dates, source) for back-tax instalments."""
    if tax["decision_due_dates"]:
        return list(tax["decision_due_dates"]), "tax_decision"
    month = tax["assessment_end_month"]
    if calendar and month:
        dates = list(calendar.get("back_tax_instalments_by_assessment_end_month", {}).get(month) or [])
        threshold = calendar.get("back_tax_two_instalments_above_cents")
        amount = tax["decision_amount_cents"]
        if dates and threshold is not None and amount is not None and amount <= threshold:
            dates = dates[:1]
        if dates:
            return dates, "calendar"
    return [], None


def tax_cycle_status(conn, customer_id, as_of, tax, calendar=None):
    """Where the customer is in the yearly Finnish income-tax cycle.

    Args:
        conn, customer_id: ledger connection and customer (used for the default
            as_of and for refund detection).
        as_of: ISO date (str) or None for the last observed ledger date.
        tax: the customer's `tax` profile dict (may be None or partial). Uses
            decision_result, decision_amount_cents, decision_due_dates,
            assessment_end_month.
        calendar: calendar dict from load_tax_calendar; None loads the file for
            as_of's year. A calendar for another year is ignored. Dates on the
            customer's tax decision always override the calendar.
    Returns dict:
        stage (one of TAX_STAGES), stage_label, as_of, next_date (ISO or None),
        next_date_label, days_until (int or None), date_source
        ("tax_decision"|"calendar"|None), calendar_verified (bool or None),
        tasks [plain sentences], decision_result, decision_amount_cents,
        refund_seen (dict from tax_refund_seen, only for refund decisions),
        check_mytax_note (str or None; set when dates come from an unverified
        calendar or are missing), footer.
        Stage rules: a refund decision is `refund_expected` until the refund is
        seen or DECISION_STAGE_GRACE_DAYS after its date; a back-tax decision is
        `back_tax_due` until that long after the last instalment. Otherwise by
        month: Jan-Mar `return_coming`, April up to the last return due date
        `check_return`, then to Oct `decision_pending` (no decision entered),
        Nov-Dec `year_end`. A decision of "none" entered during May-Oct also
        gives `year_end` (nothing left in this cycle).
    """
    tax = _clean_tax(tax)
    _, day = _as_of(conn, customer_id, as_of)
    calendar = _calendar_for(day, calendar)
    verified = calendar.get("verified") if calendar else None
    grace = timedelta(days=DECISION_STAGE_GRACE_DAYS)
    stage = next_date = next_label = date_source = None
    tasks = []
    refund_seen = None
    result_kind = tax["decision_result"]
    amount = tax["decision_amount_cents"]

    if result_kind == "refund" and amount:
        expected, source = _refund_date(tax, calendar)
        refund_seen = tax_refund_seen(conn, customer_id, tax, calendar=calendar)
        if refund_seen["seen"]:
            if date.fromisoformat(refund_seen["match"]["date"]) + grace >= day:
                stage = "refund_expected"
                tasks = ["Your tax refund of %s arrived on %s." % (_euro(refund_seen["match"]["amount_cents"]), refund_seen["match"]["date"])]
        elif expected is None or date.fromisoformat(expected) + grace >= day:
            stage = "refund_expected"
            next_date, next_label, date_source = expected, "Expected refund date", source
            tasks = ["Your tax decision shows a refund of %s." % _euro(amount)]
            if expected:
                tasks.append("It should arrive in your account on or around %s." % expected)
            else:
                tasks.append("Your refund date is on your tax decision in MyTax.")
            tasks.append("Check that your bank account number in MyTax is up to date.")
    elif result_kind == "back_tax" and amount:
        dates, source = _back_tax_dates(tax, calendar)
        if not dates or date.fromisoformat(dates[-1]) + grace >= day:
            stage = "back_tax_due"
            date_source = source
            upcoming = [value for value in dates if date.fromisoformat(value) >= day]
            next_date = upcoming[0] if upcoming else None
            next_label = "Next back-tax due date"
            tasks = ["Your tax decision shows back taxes of %s." % _euro(amount)]
            if dates:
                tasks.append("Due date%s: %s." % ("s" if len(dates) > 1 else "", ", ".join(dates)))
            else:
                tasks.append("Your due dates and payment reference are on your tax decision in MyTax.")
            tasks.append("Set money aside before each due date. The payment details are in MyTax.")

    if stage is None:
        returns = sorted(calendar.get("return_check_due_dates", [])) if calendar else []
        last_return = date.fromisoformat(returns[-1]) if returns else None
        if day.month <= 3:
            stage = "return_coming"
            if returns:
                next_date, next_label, date_source = returns[0], "Earliest return check due date", "calendar"
            tasks = [
                "Your pre-completed tax return arrives in MyTax in spring.",
                "Keep receipts for anything you may need to add or correct.",
            ]
        elif day.month == 4 and (last_return is None or day <= last_return):
            stage = "check_return"
            upcoming = [value for value in returns if date.fromisoformat(value) >= day]
            if upcoming:
                next_date, next_label, date_source = upcoming[0], "Next return check due date", "calendar"
            tasks = [
                "Check your pre-completed tax return in MyTax.",
                "Your own due date is shown on your return. Correct or add details by then; if everything is right, you do not need to do anything.",
            ]
        elif day.month <= 10 and result_kind is None:
            stage = "decision_pending"
            revised = calendar.get("revised_decision_by") if calendar else None
            month = tax["assessment_end_month"]
            if month:
                next_date, next_label = month_bounds(month)[1], "End of your tax assessment"
                date_source = "tax_decision"
            elif revised:
                next_date, next_label, date_source = revised, "Latest date for tax decisions", "calendar"
            tasks = [
                "Your tax decision will show whether you get a refund or pay back taxes.",
                "When it arrives in MyTax, you can enter the result here so I can plan for it.",
            ]
        else:
            stage = "year_end"
            tasks = [
                "Nothing more to do in this year's tax cycle.",
                "If your income changes a lot, you can change your tax card in MyTax.",
            ]

    days_until = None
    if next_date:
        days_until = (date.fromisoformat(next_date) - day).days
    check_note = None
    if (date_source == "calendar" and not verified) or (
        next_date is None and stage in {"refund_expected", "back_tax_due", "decision_pending", "return_coming", "check_return"}
    ):
        check_note = CHECK_MYTAX_NOTE
    if stage == "check_return" and calendar and not calendar.get("return_check_due_dates_verified", verified):
        check_note = CHECK_MYTAX_NOTE
    return {
        "stage": stage,
        "stage_label": _STAGE_LABELS[stage],
        "as_of": day.isoformat(),
        "next_date": next_date,
        "next_date_label": next_label if next_date else None,
        "days_until": days_until,
        "date_source": date_source,
        "calendar_verified": verified,
        "tasks": tasks,
        "decision_result": result_kind,
        "decision_amount_cents": amount,
        "refund_seen": refund_seen,
        "check_mytax_note": check_note,
        "sources": [item["url"] for item in calendar.get("sources", [])] if calendar else [],
        "not_tax_advice": True,
        "footer": TAX_FOOTER,
    }


def _balance_on(conn, customer_id, day):
    rows = transactions(conn, customer_id, None, day.isoformat())
    if not rows:
        return None, None
    return rows[-1]["balance_after_cents"], rows[-1]["date"]


def back_tax_plan(conn, customer_id, as_of, tax, calendar=None, reserve_floor_cents=0):
    """Monthly set-aside plan for back taxes from the customer's tax decision.

    Wraps tax_planning_scenario once per instalment. The amount is split equally
    over the instalments (by default 50/50 over two; any odd cent goes to the
    first); already_set_aside_cents is allocated to the earliest instalments.

    Args:
        conn, customer_id: ledger connection and customer.
        as_of: ISO date (str) or None for the last observed ledger date; used as
            reference_date and to read the current balance (latest
            balance_after_cents on or before as_of).
        tax: the customer's `tax` dict; needs decision_result "back_tax" and
            decision_amount_cents > 0. Uses decision_due_dates, else the calendar
            by assessment_end_month; already_set_aside_cents.
        calendar: optional calendar dict (default: file for as_of's year).
        reserve_floor_cents: passed through to tax_planning_scenario.
    Returns dict:
        available (bool), reason (when False), amount_cents, instalment_count,
        due_dates [ISO], date_source, current_balance_cents, balance_date,
        instalments [{number, due_date, amount_cents, already_set_aside_cents,
        status "upcoming"|"due_date_passed", scenario (tax_planning_scenario
        result or None)}], monthly_set_aside_now_cents (sum of required monthly
        set-asides of upcoming instalments), assumptions [str], footer.
    """
    tax = _clean_tax(tax)
    _, day = _as_of(conn, customer_id, as_of)
    base = {"available": False, "footer": TAX_FOOTER, "not_tax_advice": True}
    if tax["decision_result"] != "back_tax" or not tax["decision_amount_cents"]:
        return {**base, "reason": "No back taxes have been entered from your tax decision."}
    calendar = _calendar_for(day, calendar)
    dates, source = _back_tax_dates(tax, calendar)
    if not dates:
        return {
            **base,
            "reason": "I need the due dates from your tax decision, or the end month of your tax assessment.",
        }
    amount = tax["decision_amount_cents"]
    count = len(dates)
    share, odd = divmod(amount, count)
    balance, balance_date = _balance_on(conn, customer_id, day)
    set_aside_left = tax["already_set_aside_cents"] or 0
    instalments = []
    monthly_now = 0
    for index, due in enumerate(dates):
        part = share + (odd if index == 0 else 0)
        set_aside = min(set_aside_left, part)
        set_aside_left -= set_aside
        item = {
            "number": index + 1,
            "due_date": due,
            "amount_cents": part,
            "already_set_aside_cents": set_aside,
            "status": "upcoming" if date.fromisoformat(due) > day else "due_date_passed",
            "scenario": None,
        }
        if item["status"] == "upcoming" and part > 0:
            item["scenario"] = tax_planning_scenario(
                part,
                due,
                day.isoformat(),
                already_set_aside_cents=set_aside,
                current_balance_cents=balance,
                reserve_floor_cents=reserve_floor_cents,
                label="Back tax instalment %d of %d" % (index + 1, count),
            )
            monthly_now += item["scenario"]["required_monthly_set_aside_cents"]
        instalments.append(item)
    assumptions = [
        "The back-tax amount comes from the tax decision you entered",
        (
            "The amount is split equally over %d instalments" % count
            if count != 2
            else "The amount is split 50/50 over two instalments"
        ),
        "Money you already set aside counts toward the earliest instalment first",
        "Each instalment is planned separately against the same current balance",
    ]
    if source == "calendar":
        assumptions.append("Due dates come from the published calendar for your assessment end month; your tax decision shows the exact dates")
    return {
        "available": True,
        "amount_cents": amount,
        "instalment_count": count,
        "due_dates": dates,
        "date_source": source,
        "calendar_verified": calendar.get("verified") if calendar else None,
        "current_balance_cents": balance,
        "balance_date": balance_date,
        "instalments": instalments,
        "monthly_set_aside_now_cents": monthly_now,
        "assumptions": assumptions,
        "source": "user_declared",
        "not_tax_advice": True,
        "footer": TAX_FOOTER,
    }


def tax_refund_seen(conn, customer_id, tax, calendar=None):
    """Look for the declared tax refund (or an explicitly tax-labelled credit) in the ledger.

    Args:
        conn, customer_id: ledger connection and customer.
        tax: the customer's `tax` dict. A refund decision (decision_result
            "refund", decision_amount_cents) is matched against incoming
            non-salary credits within REFUND_MATCH_TOLERANCE_CENTS (one euro).
            With an expected date (decision_due_dates[0], else the calendar by
            assessment_end_month) only credits from 7 days before to 21 days
            after it count; without one any date counts.
        calendar: optional calendar dict; None loads the file for the
            assessment end month's year (or skips the calendar).
    Returns dict:
        seen (bool), matched_by ("declared_amount"|"tax_category"|None),
        match {date, amount_cents, category, transaction_ref} or None,
        expected_date (ISO or None), window {start, end} or None,
        declared_amount_cents, transaction_refs [str], reason (when not seen).
    """
    tax = _clean_tax(tax)
    account_scope(conn, customer_id)
    declared = tax["decision_amount_cents"] if tax["decision_result"] == "refund" else None
    if calendar is None:
        year = None
        if tax["assessment_end_month"]:
            year = int(tax["assessment_end_month"][:4])
        elif tax["tax_year"]:
            year = tax["tax_year"] + 1
        calendar = load_tax_calendar(year) if year else None
    expected, _ = _refund_date(tax, calendar) if declared else (None, None)
    window = None
    start = end = None
    if expected:
        anchor = date.fromisoformat(expected)
        start = (anchor - timedelta(days=REFUND_WINDOW_DAYS_BEFORE)).isoformat()
        end = (anchor + timedelta(days=REFUND_WINDOW_DAYS_AFTER)).isoformat()
        window = {"start": start, "end": end}
    credits = [
        row
        for row in transactions(conn, customer_id, start, end)
        if row["amount_cents"] > 0 and row["transaction_type"] != "salary"
    ]
    match = matched_by = None
    if declared:
        for row in credits:
            if abs(row["amount_cents"] - declared) <= REFUND_MATCH_TOLERANCE_CENTS:
                match, matched_by = row, "declared_amount"
                break
    if match is None:
        for row in credits:
            if row["category"].strip().casefold() in _EXPLICIT_TRANSACTION_CATEGORIES:
                match, matched_by = row, "tax_category"
                break
    result = {
        "seen": match is not None,
        "matched_by": matched_by,
        "match": None,
        "expected_date": expected,
        "window": window,
        "declared_amount_cents": declared,
        "transaction_refs": [],
        "observed": True,
    }
    if match is None:
        result["reason"] = (
            "No incoming payment matching your refund was found in the account."
            if declared
            else "No refund has been entered and no credit is labelled as tax."
        )
        return result
    result["match"] = {
        "date": match["date"],
        "amount_cents": match["amount_cents"],
        "category": match["category"],
        "transaction_ref": match["transaction_ref"],
    }
    result["transaction_refs"] = [match["transaction_ref"]]
    return result


def vat_learn_card(conn, customer_id, month):
    """Did-you-know card: the category with the most VAT inside its prices this month.

    Args:
        conn, customer_id: ledger connection and customer.
        month: "YYYY-MM" (must be inside the observed history; see vat.vat_lens).
    Returns dict:
        available (bool), month, period {start, end}, category,
        spending_cents (gross spending in that category with a VAT estimate),
        estimated_vat_cents, rate_display (the vat.py rate label, e.g. a single
        label, or labels joined with " and " if the category mixes rates),
        rate_labels [str], transaction_count, month_estimated_vat_cents (all
        categories), sentence (one plain English sentence), transaction_refs,
        estimated True, limitations (from vat_lens). When no purchase has a VAT
        estimate: available False and reason.
    """
    start, end = month_bounds(month)
    lens = vat_lens(conn, customer_id, start, end)
    groups = {}
    for item in lens["transactions"]:
        if item["estimated_vat_cents"] is None:
            continue
        group = groups.setdefault(
            item["category"],
            {"spending_cents": 0, "estimated_vat_cents": 0, "rates": {}, "refs": []},
        )
        group["spending_cents"] += item["gross_cents"]
        group["estimated_vat_cents"] += item["estimated_vat_cents"]
        group["rates"][item["rate_basis_points"]] = item["rate_display"]
        if item["transaction_ref"]:
            group["refs"].append(item["transaction_ref"])
    base = {"month": month, "period": {"start": start, "end": end}, "estimated": True, "limitations": lens["limitations"]}
    if not groups:
        return {**base, "available": False, "reason": "No purchases with a VAT estimate this month."}
    category = max(groups, key=lambda key: (groups[key]["estimated_vat_cents"], key))
    group = groups[category]
    labels = [group["rates"][key] for key in sorted(group["rates"])]
    rate_display = " and ".join(labels)
    sentence = "Your %s purchases of %s this month included about %s of VAT (%s), already inside the prices you paid." % (
        category, _euro(group["spending_cents"]), _euro(group["estimated_vat_cents"]), rate_display
    )
    return {
        **base,
        "available": True,
        "category": category,
        "spending_cents": group["spending_cents"],
        "estimated_vat_cents": group["estimated_vat_cents"],
        "rate_display": rate_display,
        "rate_labels": labels,
        "transaction_count": len(group["refs"]),
        "month_estimated_vat_cents": lens["estimated_vat_cents"],
        "sentence": sentence,
        "transaction_refs": group["refs"],
        "fact_id": fact_id("vat-learn-card", lens["fact_id"], category),
    }


def _without_rates(value):
    if isinstance(value, dict):
        return {key: _without_rates(item) for key, item in value.items() if key not in _AI_HIDDEN_KEYS}
    if isinstance(value, list):
        return [_without_rates(item) for item in value]
    return value


def tax_overview(conn, customer_id, as_of, tax, month=None, calendar=None):
    """Everything the "My taxes" card and the tax_overview AI tool need, in one call.

    Args:
        conn, customer_id: ledger connection and customer.
        as_of: ISO date (str) or None for the last observed ledger date.
        tax: the customer's `tax` profile dict (may be None or partial).
        month: "YYYY-MM" for the VAT card; default as_of's month. If that month
            is outside the observed history the VAT card is unavailable.
        calendar: optional calendar dict (default: file for as_of's year).
    Returns dict:
        overview (for the UI): {has_tax_data, inputs (the cleaned tax dict,
            including base_rate_bp/additional_rate_bp), withholding
            (withholding_estimate), cycle (tax_cycle_status), back_tax_plan,
            refund (tax_refund_seen), vat_card (vat_learn_card), footer}
        ai_view (for the model): the same structure with every base_rate_bp and
            additional_rate_bp key removed at any depth, plus a `basis` sentence.
    """
    clean = _clean_tax(tax)
    _, day = _as_of(conn, customer_id, as_of)
    as_of_text = day.isoformat()
    month = month or as_of_text[:7]
    try:
        vat_card = vat_learn_card(conn, customer_id, month)
    except ValueError as error:
        vat_card = {"available": False, "month": month, "reason": str(error)}
    overview = {
        "has_tax_data": any(value not in (None, []) for value in clean.values()),
        "as_of": as_of_text,
        "inputs": clean,
        "withholding": withholding_estimate(conn, customer_id, as_of_text, clean),
        "cycle": tax_cycle_status(conn, customer_id, as_of_text, clean, calendar),
        "back_tax_plan": back_tax_plan(conn, customer_id, as_of_text, clean, calendar),
        "refund": tax_refund_seen(conn, customer_id, clean, calendar=calendar),
        "vat_card": vat_card,
        "footer": TAX_FOOTER,
        "not_tax_advice": True,
    }
    ai_view = _without_rates(overview)
    ai_view["basis"] = (
        "Income tax is withheld via the tax card, so the account shows net pay only. "
        "Figures use what the customer entered from their tax card and tax decision, and salary credits in the account."
    )
    return {"overview": overview, "ai_view": ai_view}
