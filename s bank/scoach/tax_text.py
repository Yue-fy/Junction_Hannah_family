"""Finnish and Swedish text for the "My taxes" card and the VAT tile (V4 lane L).

``tax.py`` builds English sentences. These helpers rebuild the customer-facing text in
Finnish or Swedish from the structured fields of the same result (cents, dates, stage),
so no English sentence is parsed and every number keeps its FI/SV format
("1 138,27 €", "13,5 %", "5.8.2026"). English results are returned unchanged.
Vero's e-service is "OmaVero" in Finnish and "MinSkatt" in Swedish.
"""
from .labels import category_label, euros, locale_or_en, short_date

STAGE_LABELS = {
    'fi': {'return_coming': 'Esitäytetty veroilmoitus on tulossa', 'check_return': 'Tarkista veroilmoituksesi',
           'decision_pending': 'Odotetaan veropäätöstä', 'refund_expected': 'Veronpalautus tulossa',
           'back_tax_due': 'Jäännösveroa maksettavana', 'year_end': 'Verovuosi on lopuillaan'},
    'sv': {'return_coming': 'Den förhandsifyllda skattedeklarationen är på väg', 'check_return': 'Dags att granska din skattedeklaration',
           'decision_pending': 'Väntar på beskattningsbeslutet', 'refund_expected': 'Skatteåterbäring på väg',
           'back_tax_due': 'Kvarskatt att betala', 'year_end': 'Skatteåret går mot sitt slut'},
}
NEXT_DATE_LABELS = {
    'Expected refund date': ('Palautuksen arvioitu maksupäivä', 'Väntat datum för återbäringen'),
    'Next back-tax due date': ('Jäännösveron seuraava eräpäivä', 'Nästa förfallodag för kvarskatten'),
    'Earliest return check due date': ('Veroilmoituksen tarkistuksen aikaisin määräpäivä', 'Tidigaste sista dag att granska deklarationen'),
    'Next return check due date': ('Veroilmoituksen tarkistuksen seuraava määräpäivä', 'Nästa sista dag att granska deklarationen'),
    'End of your tax assessment': ('Verotuksesi päättyy', 'Din beskattning avslutas'),
    'Latest date for tax decisions': ('Veropäätökset viimeistään', 'Beskattningsbesluten senast'),
}
TEXT = {
    'footer': ('Arvio antamiesi tietojen perusteella. Virallinen tieto on veropäätöksessäsi OmaVerossa.',
               'Uppskattning utifrån det du har angett. Den officiella uppgiften finns i ditt beskattningsbeslut i MinSkatt.'),
    'check_mytax': ('Tarkista tarkat päivät OmaVerosta.', 'Kontrollera de exakta datumen i MinSkatt.'),
    'missing': ('Tililläsi näkyy palkka verojen jälkeen, joten tarvitsen bruttopalkkasi palkkalaskelmasta ja verokorttisi pidätysprosentin.',
                'Kontot visar lönen efter skatt, så jag behöver din bruttolön från lönebeskedet och skattesatsen på ditt skattekort.'),
    'flow': ('Bruttopalkka noin {gross} → ennakonpidätys noin {withheld} → tilille {received}',
             'Bruttolön cirka {gross} → förskottsinnehållning cirka {withheld} → till kontot {received}'),
    'gap': ('Tilillesi tullut palkka poikkeaa summasta brutto miinus ennakonpidätys. Arviossa ei ole mukana työeläke- ja työttömyysvakuutusmaksuja eikä muita palkasta tehtäviä vähennyksiä.',
            'Lönen som kommit in skiljer sig från brutto minus förskottsinnehållning. Arbetspensions- och arbetslöshetsförsäkringsavgifter och andra avdrag från lönen ingår inte i uppskattningen.'),
    'no_salary': ('Tälle verovuodelle ei ole vielä löytynyt palkkoja tililtäsi.', 'Inga löneinsättningar har hittats på kontot för det här skatteåret än.'),
    'refund_arrived': ('Veronpalautuksesi {amount} saapui {date}.', 'Din skatteåterbäring på {amount} kom {date}.'),
    'refund_shows': ('Veropäätöksesi mukaan saat palautusta {amount}.', 'Enligt ditt beskattningsbeslut får du {amount} tillbaka.'),
    'refund_date': ('Sen pitäisi näkyä tililläsi {date} tienoilla.', 'Den bör komma till ditt konto runt {date}.'),
    'refund_no_date': ('Palautuksen maksupäivä on veropäätöksessäsi OmaVerossa.', 'Datumet för återbäringen finns i ditt beskattningsbeslut i MinSkatt.'),
    'refund_account': ('Tarkista, että tilinumerosi on OmaVerossa ajan tasalla.', 'Kontrollera att ditt kontonummer i MinSkatt är uppdaterat.'),
    'back_tax_shows': ('Veropäätöksesi mukaan maksettavaa jäännösveroa on {amount}.', 'Enligt ditt beskattningsbeslut ska du betala {amount} i kvarskatt.'),
    'due_one': ('Eräpäivä: {dates}.', 'Förfallodag: {dates}.'),
    'due_many': ('Eräpäivät: {dates}.', 'Förfallodagar: {dates}.'),
    'due_unknown': ('Eräpäivät ja viitenumero ovat veropäätöksessäsi OmaVerossa.', 'Förfallodagarna och referensnumret finns i ditt beskattningsbeslut i MinSkatt.'),
    'back_tax_set_aside': ('Varaa rahat ennen jokaista eräpäivää. Maksutiedot löydät OmaVerosta.', 'Lägg undan pengar före varje förfallodag. Betalningsuppgifterna finns i MinSkatt.'),
    'return_coming_1': ('Esitäytetty veroilmoituksesi tulee OmaVeroon keväällä.', 'Din förhandsifyllda skattedeklaration kommer till MinSkatt på våren.'),
    'return_coming_2': ('Säästä kuitit asioista, joita saatat joutua lisäämään tai korjaamaan.', 'Spara kvitton på sådant som du kan behöva lägga till eller rätta.'),
    'check_return_1': ('Tarkista esitäytetty veroilmoituksesi OmaVerossa.', 'Granska din förhandsifyllda skattedeklaration i MinSkatt.'),
    'check_return_2': ('Oma määräpäiväsi näkyy veroilmoituksessa. Korjaa tai lisää tiedot siihen mennessä – jos kaikki on oikein, sinun ei tarvitse tehdä mitään.',
                       'Din egen sista dag står på deklarationen. Rätta eller lägg till uppgifter före den – om allt stämmer behöver du inte göra något.'),
    'pending_1': ('Veropäätöksestä näet, saatko palautusta vai maksatko jäännösveroa.', 'Av beskattningsbeslutet ser du om du får återbäring eller ska betala kvarskatt.'),
    'pending_2': ('Kun päätös tulee OmaVeroon, voit kirjata tuloksen tänne, niin varaudun siihen.', 'När beslutet kommer till MinSkatt kan du föra in resultatet här, så tar jag med det i planen.'),
    'year_end_1': ('Tämän vuoden verotuksessa ei ole enää tehtävää.', 'Det finns inget mer att göra i årets beskattning.'),
    'year_end_2': ('Jos tulosi muuttuvat paljon, voit muuttaa verokorttiasi OmaVerossa.', 'Om din inkomst ändras mycket kan du ändra ditt skattekort i MinSkatt.'),
    'no_back_tax': ('Veropäätöksestäsi ei ole kirjattu jäännösveroa.', 'Ingen kvarskatt har förts in från ditt beskattningsbeslut.'),
    'need_dates': ('Tarvitsen veropäätöksesi eräpäivät tai verotuksesi päättymiskuukauden.', 'Jag behöver förfallodagarna från ditt beskattningsbeslut eller den månad då din beskattning avslutas.'),
    'vat_none': ('Tässä kuussa ei ollut ostoksia, joille voisi arvioida arvonlisäveron.', 'Den här månaden fanns inga köp där momsen kan uppskattas.'),
    'vat_sentence': ('{category}: ostoksiisi {spent} sisältyi tässä kuussa noin {vat} arvonlisäveroa ({rate}). Se on jo hinnoissa, jotka maksoit.',
                     '{category}: i dina köp för {spent} ingick den här månaden ungefär {vat} moms ({rate}). Den ingår redan i priserna du betalade.'),
}


def _say(locale, key, **values):
    fi, sv = TEXT[key]
    return (fi if locale == 'fi' else sv).format(**values)


def rate_text(rate_display, locale):
    """'13.5% and 25.5%' → '13,5 % ja 25,5 %' (FI) / '13,5 % och 25,5 %' (SV); EN unchanged."""
    if not isinstance(rate_display, str) or locale_or_en(locale) == 'en':
        return rate_display
    parts = [part.strip() for part in rate_display.split(' and ')]
    parts = [part.replace('%', '').strip().replace('.', ',') + ' %' if part.endswith('%') else part for part in parts]
    return (' ja ' if locale == 'fi' else ' och ').join(parts)


def localize_vat_card(card, locale):
    """Return the VAT tile dict with rate_display/rate_labels/sentence/reason in FI or SV."""
    if locale_or_en(locale) == 'en' or not isinstance(card, dict):
        return card
    out = dict(card)
    if out.get('available'):
        out['rate_display'] = rate_text(card.get('rate_display'), locale)
        out['rate_labels'] = [rate_text(label, locale) for label in card.get('rate_labels') or []]
        out['category_label'] = category_label(card.get('category'), locale)
        if all(isinstance(card.get(key), int) for key in ('spending_cents', 'estimated_vat_cents')):
            out['sentence'] = _say(locale, 'vat_sentence', category=out['category_label'], spent=euros(card['spending_cents'], locale, True),
                                   vat=euros(card['estimated_vat_cents'], locale, True), rate=out['rate_display'])
    elif isinstance(out.get('reason'), str) and out['reason'].startswith('No purchases with a VAT estimate'):
        out['reason'] = _say(locale, 'vat_none')
    return out


def _cycle(cycle, locale):
    out = dict(cycle)
    stage = cycle.get('stage')
    if stage in STAGE_LABELS[locale]:
        out['stage_label'] = STAGE_LABELS[locale][stage]
    label = cycle.get('next_date_label')
    if label in NEXT_DATE_LABELS:
        out['next_date_label'] = NEXT_DATE_LABELS[label][0 if locale == 'fi' else 1]
    if cycle.get('check_mytax_note'):
        out['check_mytax_note'] = _say(locale, 'check_mytax')
    if cycle.get('footer'):
        out['footer'] = _say(locale, 'footer')
    money = lambda cents: euros(cents, locale, True)
    amount = cycle.get('decision_amount_cents')
    tasks = cycle.get('tasks') or []
    english = ' '.join(t for t in tasks if isinstance(t, str))
    rebuilt = None
    if stage == 'refund_expected':
        seen = cycle.get('refund_seen') or {}
        if seen.get('seen') and seen.get('match'):
            rebuilt = [_say(locale, 'refund_arrived', amount=money(seen['match']['amount_cents']), date=short_date(seen['match']['date'], locale))]
        elif isinstance(amount, int):
            rebuilt = [_say(locale, 'refund_shows', amount=money(amount))]
            date = cycle.get('next_date')
            rebuilt.append(_say(locale, 'refund_date', date=short_date(date, locale)) if date else _say(locale, 'refund_no_date'))
            rebuilt.append(_say(locale, 'refund_account'))
    elif stage == 'back_tax_due' and isinstance(amount, int):
        rebuilt = [_say(locale, 'back_tax_shows', amount=money(amount))]
        dates = [word.rstrip('.,') for word in english.split() if len(word.rstrip('.,')) == 10 and word[4:5] == '-' and word[:4].isdigit()]
        if dates:
            rebuilt.append(_say(locale, 'due_many' if len(dates) > 1 else 'due_one', dates=', '.join(short_date(d, locale) for d in dates)))
        else:
            rebuilt.append(_say(locale, 'due_unknown'))
        rebuilt.append(_say(locale, 'back_tax_set_aside'))
    elif stage == 'return_coming':
        rebuilt = [_say(locale, 'return_coming_1'), _say(locale, 'return_coming_2')]
    elif stage == 'check_return':
        rebuilt = [_say(locale, 'check_return_1'), _say(locale, 'check_return_2')]
    elif stage == 'decision_pending':
        rebuilt = [_say(locale, 'pending_1'), _say(locale, 'pending_2')]
    elif stage == 'year_end':
        rebuilt = [_say(locale, 'year_end_1'), _say(locale, 'year_end_2')]
    if rebuilt is not None and tasks:
        out['tasks'] = rebuilt
    return out


def _withholding(w, locale):
    out = dict(w)
    if out.get('footer'):
        out['footer'] = _say(locale, 'footer')
    if not w.get('available'):
        if isinstance(w.get('reason'), str) and w['reason'].startswith('Your account shows salary after tax'):
            out['reason'] = _say(locale, 'missing')
        return out
    flow = w.get('flow') or {}
    if all(isinstance(flow.get(key), int) for key in ('gross_cents', 'withheld_cents', 'received_cents')):
        out['flow'] = {**flow, 'text': _say(locale, 'flow', gross=euros(flow['gross_cents'], locale, True),
                                            withheld=euros(flow['withheld_cents'], locale, True),
                                            received=euros(flow['received_cents'], locale, True))}
    notes = []
    for note in w.get('notes') or []:
        if isinstance(note, str) and note.startswith('Your received salary differs'):
            notes.append(_say(locale, 'gap'))
        elif isinstance(note, str) and note.startswith('No salary credits were found'):
            notes.append(_say(locale, 'no_salary'))
        else:
            notes.append(note)
    out['notes'] = notes
    return out


def _back_tax_plan(plan, locale):
    out = dict(plan)
    reason = plan.get('reason')
    if isinstance(reason, str):
        if reason.startswith('No back taxes have been entered'):
            out['reason'] = _say(locale, 'no_back_tax')
        elif reason.startswith('I need the due dates'):
            out['reason'] = _say(locale, 'need_dates')
    return out


def localize_tax_overview(overview, locale):
    """The tax_overview()['overview'] dict with its customer-facing text in FI or SV.

    Numbers, dates, stages and ids are untouched; only text fields are replaced.
    """
    locale = locale_or_en(locale)
    if locale == 'en' or not isinstance(overview, dict):
        return overview
    out = dict(overview)
    if isinstance(out.get('footer'), str):
        out['footer'] = _say(locale, 'footer')
    if isinstance(out.get('withholding'), dict):
        out['withholding'] = _withholding(out['withholding'], locale)
    if isinstance(out.get('cycle'), dict):
        out['cycle'] = _cycle(out['cycle'], locale)
    if isinstance(out.get('back_tax_plan'), dict):
        out['back_tax_plan'] = _back_tax_plan(out['back_tax_plan'], locale)
    if isinstance(out.get('vat_card'), dict):
        out['vat_card'] = localize_vat_card(out['vat_card'], locale)
    return out
