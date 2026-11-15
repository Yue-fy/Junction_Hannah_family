"""Customer-facing labels and number formats shared by server-side text (EN / FI / SV).

Category names follow the web app's own labels (web/experience.js 'category.*'), so a
category reads the same on every screen. Money is integer cents.
"""
from decimal import ROUND_HALF_UP, Decimal

LOCALES = ('en', 'fi', 'sv')

CATEGORY_LABELS = {
    'Housing': ('Housing', 'Asuminen', 'Boende'),
    'Utilities': ('Bills', 'Laskut', 'Räkningar'),
    'Groceries': ('Groceries', 'Ruokaostokset', 'Matinköp'),
    'Transportation': ('Transport', 'Liikenne', 'Transport'),
    'Restaurants': ('Eating out', 'Ravintolat', 'Restaurang'),
    'Health': ('Health', 'Terveys', 'Hälsa'),
    'Home & Tech': ('Home & tech', 'Koti ja tekniikka', 'Hem och teknik'),
    'Lifestyle': ('Shopping', 'Ostokset', 'Shopping'),
    'Entertainment': ('Entertainment', 'Viihde', 'Nöjen'),
    'Travel': ('Travel', 'Matkailu', 'Resor'),
    'Salary': ('Salary', 'Palkka', 'Lön'),
    'Other Income': ('Other income', 'Muut tulot', 'Övriga inkomster'),
    'Invest Deposit': ('Investments', 'Sijoitukset', 'Investeringar'),
    'Invest Withdraw': ('From investments', 'Nostot sijoituksista', 'Uttag från investeringar'),
}


def locale_or_en(locale):
    return locale if locale in LOCALES else 'en'


def category_label(category, locale='en'):
    """Localized category name; unknown categories are returned unchanged."""
    labels = CATEGORY_LABELS.get(category)
    return labels[LOCALES.index(locale_or_en(locale))] if labels else category


def _group(number, separator):
    text = '{:,}'.format(number)
    return text.replace(',', separator)


def euros(cents, locale='en', decimals=False):
    """'€2,365' (EN) or '2 365 €' (FI/SV, no-break spaces). Whole euros unless decimals=True."""
    locale = locale_or_en(locale)
    value = Decimal(int(cents)) / 100
    sign = '−' if value < 0 else ''
    value = abs(value)
    if decimals:
        whole, frac = divmod(int((value * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)), 100)
        tail = ('.' if locale == 'en' else ',') + '%02d' % frac
    else:
        whole, tail = int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)), ''
    if locale == 'en':
        return '%s€%s%s' % (sign, _group(whole, ','), tail)
    return '%s%s%s €' % (sign, _group(whole, ' '), tail)


def percent(value, locale='en', digits=1):
    """'9.6%' (EN) or '9,6 %' (FI/SV). Trailing zeros are dropped."""
    text = ('{:.%df}' % digits).format(float(value)).rstrip('0').rstrip('.') if digits else str(int(round(value)))
    if locale_or_en(locale) == 'en':
        return text + '%'
    return text.replace('.', ',') + ' %'


def day_ordinal(day, locale='en'):
    """'5th' (EN), '5.' (FI), '5:e' / '1:a' (SV)."""
    locale = locale_or_en(locale)
    if locale == 'fi':
        return '%s.' % day
    if locale == 'sv':
        return '%s:%s' % (day, 'a' if day % 10 in (1, 2) and day % 100 not in (11, 12) else 'e')
    suffix = 'th' if 10 <= day % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return '%s%s' % (day, suffix)


def short_date(iso, locale='en'):
    """ISO date for EN (unchanged), '15.8.2026' for FI/SV."""
    if locale_or_en(locale) == 'en':
        return iso
    year, month, day = iso.split('-')
    return '%d.%d.%s' % (int(day), int(month), year)
