/** Plain-language summaries of returned facts. No financial model or UI state lives here. */
const integer = Number.isSafeInteger;
const plain = value => typeof value === 'string'
  ? value.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim() : '';
const key = value => plain(value).toLocaleLowerCase().replace(/[.!?]+$/, '');

function paragraphs(values) {
  const result = [], seen = new Set();
  for (const value of values) {
    const text = plain(value), normalized = key(text);
    if (text && !seen.has(normalized)) { result.push(text); seen.add(normalized); }
  }
  return result.length > 3 ? [...result.slice(0, 2), result.slice(2).join(' ')] : result;
}

const genericIntros = new Set([
  'Here is what the selected records show.',
  'Here are the exact observed results for the selected category and period.',
  'This is an unsaved planning preview based on observed spending in the selected category.',
  'This is a neutral breakdown of observed spending across the learning baskets, not a score or judgment.',
  'This estimate protects the reserve, qualified recurring outflows, and a buffer based on earlier unscheduled spending.',
  'These are observed contributions and withdrawals, not portfolio value or performance.',
  'Tässä ovat valittujen tietojen tulokset.',
  'Tässä ovat valitun luokan ja ajanjakson tarkat havaitut tulokset.',
  'Tämä on tallentamaton suunnitteluarvio, joka perustuu valitun luokan havaittuihin menoihin.',
  'Tämä on neutraali erittely havaituista menoista oppimiskoreittain, ei pisteytys tai arvio sinusta.',
  'Arvio suojaa vararahasi, tunnistetut toistuvat menot ja aiempaan aikatauluttamattomaan kulutukseen perustuvan varan.',
  'Nämä ovat havaitut sijoitussiirrot ja nostot, eivät salkun arvoa tai tuottoa.',
  'Här är vad de valda uppgifterna visar.',
  'Här är de exakta observerade resultaten för den valda kategorin och perioden.',
  'Det här är en osparad planeringsöversikt som bygger på observerade utgifter i den valda kategorin.',
  'Det här är en neutral uppdelning av observerade utgifter i lärandekorgarna, inte ett betyg eller omdöme.',
  'Uppskattningen skyddar bufferten, kvalificerade återkommande utflöden och ett utrymme baserat på tidigare ej schemalagda utgifter.',
  'Det här är observerade insättningar och uttag, inte portföljvärde eller avkastning.',
].map(key));

/**
 * Return up to three plain-text paragraphs, with the requested fact first.
 * The caller supplies its existing locale formatters and escapes text for HTML.
 * Explicit null values remain unavailable; they never fall back to zero.
 */
export function coachNarrative(response = {}, options = {}) {
  const locale = ['en', 'fi', 'sv'].includes(options.locale) ? options.locale : 'en';
  const l = (en, fi, sv) => ({en, fi, sv}[locale]);
  const money = options.money || (cents => new Intl.NumberFormat(locale, {style:'currency',currency:'EUR'}).format(cents / 100));
  const date = value => value ? plain((options.dateLabel || (item => item.slice(0, 10)))(value)) : '';
  const month = value => value ? plain((options.monthLabel || (item => item))(value)) : '';
  const category = value => plain((options.categoryName || (item => item))(value || ''));
  const number = value => new Intl.NumberFormat(locale, {maximumFractionDigits:10}).format(value);
  const unavailable = l('unavailable', 'ei saatavilla', 'saknas');
  const amount = value => integer(value) ? plain(money(value)) : unavailable;
  const flow = value => options.flowName ? plain(options.flowName(value)) : ({
    income:l('Income', 'Tulot', 'Inkomster'),
    fixed_obligation:l('must-pays', 'pakolliset kuukausimenot', 'fasta måsten'),
    flexible_essential:l('surprise must-pays', 'yllättävät pakolliset menot', 'oväntade måsten'),
    discretionary:l('little leaks', 'arjen pikkumenot', 'vardagens småutgifter'),
    saving_or_transfer:l('saving and transfers', 'säästäminen ja siirrot', 'sparande och överföringar'),
  }[value] || plain(value));
  const list = values => new Intl.ListFormat(locale, {style:'long',type:'conjunction'}).format(values.filter(Boolean));
  const supplied = paragraphs([
    ...(response.explanation_blocks || []).map(block => block?.text),
    response.clarification_question,
  ]);
  if (response.needs_clarification || !response.tool_result ||
      response.clarification_code === 'planned_purchase_preview' ||
      response.tool_kind === 'planned_purchase_preview') return supplied;

  const result = response.tool_result, scope = response.query_scope || result.query_scope || {};
  const filters = scope.filters || result.filters || {};
  const periodOf = (item, resolved = {}, fallback = true) => {
    const start = resolved.start || item.start, end = resolved.end || item.end;
    if (start && end) return date(start) + '–' + date(end);
    return month(item.period || item.month || (fallback ? response.parameters?.period || options.selectedMonth : '')) ||
      l('the returned period', 'palautettu ajanjakso', 'den angivna perioden');
  };
  const period = periodOf(result, scope);
  const during = value => l('for ' + value, 'ajanjaksolla ' + value, 'under ' + value);
  const types = {
    salary:l('salary', 'palkka', 'lön'),
    other_income:l('other income', 'muut tulot', 'övriga inkomster'),
    purchase:l('purchases', 'ostokset', 'köp'),
    housing_payment:l('housing payments', 'asumismaksut', 'boendebetalningar'),
    utilities_payment:l('utility payments', 'käyttölaskut', 'driftskostnader'),
    investment_deposit:l('investment deposits', 'sijoitussiirrot', 'investeringsinsättningar'),
    investment_withdrawal:l('investment withdrawals', 'sijoitusnostot', 'investeringsuttag'),
  };
  const concepts = {
    Taxi:l('Taxi', 'Taksi', 'Taxi'),
    Pharmacy:l('Pharmacy', 'Apteekki', 'Apotek'),
    Doctor:l('Doctor', 'Lääkäri', 'Läkare'),
    Dentist:l('Dentist', 'Hammaslääkäri', 'Tandläkare'),
    'All spending':l('consumer spending', 'kulutusmenot', 'konsumtionsutgifter'),
    'All outflows':l('all outgoing payments', 'kaikki lähtevät maksut', 'alla utgående betalningar'),
    'All inflows':l('all incoming payments', 'kaikki saapuvat maksut', 'alla inkommande betalningar'),
    'Income received':l('income', 'tulot', 'inkomster'),
  };
  const selected = Object.entries(filters).map(([name, value]) => {
    if (name === 'category') return category(value);
    if (name === 'role') return flow(value);
    if (name === 'transaction_type') return types[value] || plain(value);
    if (name === 'consumption_only') return concepts['All spending'];
    if (name === 'mcc_code') return concepts[scope.concept] || plain(scope.concept) ||
      l('merchant category ' + value, 'kauppiasluokka ' + value, 'handlarkategori ' + value);
    if (name === 'merchant_id') return l('merchant ' + value, 'kauppias ' + value, 'handlare ' + value);
    return '';
  });
  const label = list(selected) || concepts[scope.concept] || category(scope.concept) ||
    l('the selected payments', 'valitut maksut', 'de valda betalningarna');
  const field = (name, fallback) => result[name] === undefined ? fallback : result[name];
  const incomeDefinition = () => {
    if (scope.concept === 'All inflows') return l(
      'This includes incoming transfers and is not earned income.',
      'Summa sisältää saapuvat siirrot, eikä se tarkoita ansiotuloja.',
      'Detta inkluderar inkommande överföringar och är inte arbetsinkomst.');
    if (filters.transaction_type === 'investment_withdrawal') return l(
      'Investment withdrawals are transfers, not investment returns or earnings.',
      'Sijoitusnostot ovat siirtoja, eivät sijoitustuottoa tai ansiotuloa.',
      'Investeringsuttag är överföringar, inte avkastning eller arbetsinkomst.');
    if (filters.role === 'income') return l(
      'This includes salary and other income; saving and investment transfers are separate. Credited amounts do not establish gross pay before tax.',
      'Summa sisältää palkan ja muut tulot. Säästö- ja sijoitussiirrot ovat erillisiä, eikä tilille maksetuista summista voi päätellä bruttopalkkaa.',
      'Detta inkluderar lön och övriga inkomster; spar- och investeringsöverföringar hålls åtskilda. Insatta belopp fastställer inte bruttolön före skatt.');
    return l(
      'These are recorded credits to this account, not gross pay before tax.',
      'Nämä ovat tälle tilille kirjattuja tuloja, eivät bruttopalkkaa ennen veroja.',
      'Detta är registrerade insättningar på kontot, inte bruttolön före skatt.');
  };
  let answer = [];

  if (response.tool_kind === 'transaction_statistics') {
    const metric = scope.metric || result.metric || 'outflow_total';
    const empty = result.has_transactions === false || result.transaction_count === 0;
    if (empty && filters.mcc_code) {
      answer = [l(
        'I found no payments identified as ' + label + ' ' + during(period) + '.',
        'Luokkaan ' + label + ' tunnistettuja maksuja ei löytynyt ' + during(period) + '.',
        'Jag hittade inga betalningar identifierade som ' + label + ' ' + during(period) + '.'),
      l('Missing or different merchant codes may hide this spending; this does not prove that none occurred.',
        'Puuttuvat tai erilaiset kauppiaskoodit voivat peittää menoja. Tämä ei todista, ettei tällaisia menoja ollut.',
        'Saknade eller andra handlarkoder kan dölja utgifter; detta bevisar inte att inga sådana utgifter förekom.')];
    } else if (metric === 'inflow_total') {
      const value = field('metric_value_cents', result.inflow_total_cents);
      const count = integer(result.inflow_count) ? l(
        ' across ' + number(result.inflow_count) + (result.inflow_count === 1 ? ' incoming payment' : ' incoming payments'),
        ', yhteensä ' + number(result.inflow_count) + (result.inflow_count === 1 ? ' saapuva maksu' : ' saapuvaa maksua'),
        ' fördelat på ' + number(result.inflow_count) + (result.inflow_count === 1 ? ' inkommande betalning' : ' inkommande betalningar')) : '';
      answer = [integer(value) ? l(
        'You received ' + amount(value) + ' in ' + label + ' ' + during(period) + count + '.',
        'Tilille saapui ' + amount(value) + ' (' + label + ') ' + during(period) + count + '.',
        'Du fick ' + amount(value) + ' till kontot (' + label + ') ' + during(period) + count + '.')
        : l('The credited amount for ' + label + ' is unavailable ' + during(period) + '.',
          'Tilille saapunut summa (' + label + ') ei ole saatavilla ' + during(period) + '.',
          'Det insatta beloppet för ' + label + ' saknas ' + during(period) + '.'), incomeDefinition()];
    } else if (metric === 'average_outflow') {
      const value = field('metric_value_cents', result.average_outflow_cents);
      answer = [integer(value) ? l(
        'Your average outgoing payment for ' + label + ' was ' + amount(value) + ' ' + during(period) + '.',
        'Keskimääräinen lähtevä maksu (' + label + ') oli ' + amount(value) + ' ' + during(period) + '.',
        'Din genomsnittliga utgående betalning för ' + label + ' var ' + amount(value) + ' ' + during(period) + '.')
        : l('The average outgoing payment for ' + label + ' is unavailable ' + during(period) + '.',
          'Lähtevien maksujen keskiarvo (' + label + ') ei ole saatavilla ' + during(period) + '.',
          'Genomsnittet för utgående betalningar för ' + label + ' saknas ' + during(period) + '.')];
      if (integer(value) && integer(result.outflow_count)) answer[0] += ' ' + l(
        'It is based on ' + number(result.outflow_count) + (result.outflow_count === 1 ? ' payment.' : ' payments.'),
        'Se perustuu ' + number(result.outflow_count) + ' maksuun.',
        'Det bygger på ' + number(result.outflow_count) + (result.outflow_count === 1 ? ' betalning.' : ' betalningar.'));
    } else if (metric === 'transaction_count') {
      const count = field('metric_value_count', result.outflow_count);
      answer = [integer(count) ? l(
        'You made ' + number(count) + (count === 1 ? ' outgoing payment for ' : ' outgoing payments for ') + label + ' ' + during(period) + '.',
        'Lähteviä maksuja (' + label + ') oli ' + number(count) + ' ' + during(period) + '.',
        'Du gjorde ' + number(count) + (count === 1 ? ' utgående betalning för ' : ' utgående betalningar för ') + label + ' ' + during(period) + '.')
        : l('The outgoing payment count for ' + label + ' is unavailable ' + during(period) + '.',
          'Lähtevien maksujen määrä (' + label + ') ei ole saatavilla ' + during(period) + '.',
          'Antalet utgående betalningar för ' + label + ' saknas ' + during(period) + '.')];
    } else if (metric === 'largest_outflow') {
      const value = field('metric_value_cents', result.largest_outflow?.amount_cents);
      const day = date(result.largest_outflow?.date);
      answer = [integer(value) ? l(
        'Your largest recorded outgoing payment for ' + label + ' was ' + amount(value) + (day ? ' on ' + day : '') + ' ' + during(period) + '.',
        'Suurin kirjattu lähtevä maksu (' + label + ') oli ' + amount(value) + (day ? ' päivänä ' + day : '') + ' ' + during(period) + '.',
        'Din största registrerade utgående betalning för ' + label + ' var ' + amount(value) + (day ? ' den ' + day : '') + ' ' + during(period) + '.')
        : l('A largest outgoing payment for ' + label + ' is unavailable ' + during(period) + '.',
          'Suurinta lähtevää maksua (' + label + ') ei ole saatavilla ' + during(period) + '.',
          'Någon största utgående betalning för ' + label + ' finns inte tillgänglig ' + during(period) + '.')];
    } else {
      const value = field('metric_value_cents', metric === 'consumption_total' ? result.consumption_cents : result.outflow_total_cents);
      const count = integer(result.outflow_count) ? l(
        ' across ' + number(result.outflow_count) + (result.outflow_count === 1 ? ' outgoing payment' : ' outgoing payments'),
        ', yhteensä ' + number(result.outflow_count) + (result.outflow_count === 1 ? ' lähtevä maksu' : ' lähtevää maksua'),
        ' fördelat på ' + number(result.outflow_count) + (result.outflow_count === 1 ? ' utgående betalning' : ' utgående betalningar')) : '';
      const transferOrAllOutflows = metric === 'outflow_total' && (!Object.keys(filters).length ||
        scope.concept === 'All outflows' || filters.role === 'saving_or_transfer' ||
        ['investment_deposit', 'investment_withdrawal', 'salary_sweep'].includes(filters.transaction_type));
      answer = [integer(value) ? transferOrAllOutflows ? l(
        'Outgoing payments for ' + label + ' totaled ' + amount(value) + ' ' + during(period) + count + '.',
        'Lähtevät maksut (' + label + ') olivat yhteensä ' + amount(value) + ' ' + during(period) + count + '.',
        'Utgående betalningar för ' + label + ' uppgick till ' + amount(value) + ' ' + during(period) + count + '.') : l(
        'You spent ' + amount(value) + ' on ' + label + ' ' + during(period) + count + '.',
        'Käytit ' + amount(value) + ' (' + label + ') ' + during(period) + count + '.',
        'Du spenderade ' + amount(value) + ' på ' + label + ' ' + during(period) + count + '.')
        : l('Recorded spending for ' + label + ' is unavailable ' + during(period) + '.',
          'Kirjattu kulutus (' + label + ') ei ole saatavilla ' + during(period) + '.',
          'Registrerade utgifter för ' + label + ' saknas ' + during(period) + '.')];
      if (metric === 'consumption_total') answer.push(l(
        'Saving and investment transfers are excluded from this spending total.',
        'Säästö- ja sijoitussiirrot eivät sisälly tähän kulutussummaan.',
        'Spar- och investeringsöverföringar ingår inte i denna utgiftssumma.'));
      else if (transferOrAllOutflows) answer.push(l(
        'This outgoing total can include saving and investment transfers, which are not consumption. Incoming payments are separate.',
        'Lähtevä summa voi sisältää säästö- ja sijoitussiirtoja, jotka eivät ole kulutusta. Saapuvat maksut ovat erillisiä.',
        'Det utgående beloppet kan innehålla spar- och investeringsöverföringar, som inte är konsumtion. Inkommande betalningar hålls åtskilda.'));
      else if (result.inflow_total_cents > 0 || !Object.keys(filters).length) answer.push(l(
        'This is outgoing money before refunds; incoming payments are separate.',
        'Tämä on lähtevää rahaa ennen palautuksia. Saapuvat maksut ovat erillisiä.',
        'Detta är utgående pengar före återbetalningar; inkommande betalningar hålls åtskilda.'));
    }
  } else if (response.tool_kind === 'spending_comparison' || response.tool_kind === 'transaction_statistics_comparison') {
    const legacy = response.tool_kind === 'spending_comparison';
    const current = result.current || {}, previous = result.previous || result.comparison || {};
    const metric = legacy ? 'outflow_total' : scope.metric || 'outflow_total';
    const metricField = {inflow_total:'inflow_total_cents',outflow_total:'outflow_total_cents',consumption_total:'consumption_cents',average_outflow:'average_outflow_cents',transaction_count:'outflow_count'}[metric];
    const valueOf = item => legacy ? item.total_cents : metric === 'largest_outflow' ? item.largest_outflow?.amount_cents : item[metricField];
    const valueText = value => metric === 'transaction_count' ? integer(value) ? number(value) : unavailable : amount(value);
    const description = metric === 'inflow_total' ? l('Money received', 'Saapunut raha', 'Mottagna pengar')
      : metric === 'average_outflow' ? l('Average outgoing payment', 'Keskimääräinen lähtevä maksu', 'Genomsnittlig utgående betalning')
      : metric === 'transaction_count' ? l('Outgoing payment count', 'Lähtevien maksujen määrä', 'Antal utgående betalningar')
      : metric === 'largest_outflow' ? l('Largest outgoing payment', 'Suurin lähtevä maksu', 'Största utgående betalning')
      : l('Recorded spending', 'Kirjatut menot', 'Registrerade utgifter');
    const comparisonLabel = legacy && !selected.length ? category('Restaurants') : label;
    answer = [l(
      description + ' for ' + comparisonLabel + ' was ' + valueText(valueOf(current)) + ' ' + during(periodOf(current, {}, false)) + ', compared with ' + valueText(valueOf(previous)) + ' ' + during(periodOf(previous, {}, false)) + '.',
      description + ' (' + comparisonLabel + ') oli ' + valueText(valueOf(current)) + ' ' + during(periodOf(current, {}, false)) + ' ja vertailujaksolla ' + periodOf(previous, {}, false) + ' ' + valueText(valueOf(previous)) + '.',
      description + ' för ' + comparisonLabel + ' var ' + valueText(valueOf(current)) + ' ' + during(periodOf(current, {}, false)) + ', jämfört med ' + valueText(valueOf(previous)) + ' ' + during(periodOf(previous, {}, false)) + '.')];
    const delta = legacy ? result.delta_cents : metric === 'outflow_total' ? result.outflow_delta_cents : metric === 'consumption_total' ? result.consumption_delta_cents : undefined;
    if (integer(delta)) answer[0] += ' ' + (delta === 0 ? l('The total was unchanged.', 'Summa ei muuttunut.', 'Summan var oförändrad.') : l(
      'That is ' + amount(Math.abs(delta)) + (delta > 0 ? ' higher.' : ' lower.'),
      'Muutos oli ' + amount(Math.abs(delta)) + (delta > 0 ? ' ylöspäin.' : ' alaspäin.'),
      'Det är ' + amount(Math.abs(delta)) + (delta > 0 ? ' högre.' : ' lägre.')));
    if (metric === 'inflow_total') answer.push(incomeDefinition());
  } else if (response.tool_kind === 'spending_adjustment_preview') {
    const value = result.modeled_monthly_contribution_cents, base = result.adjustable_base_cents;
    const percent = /^\d+(?:\.\d+)?$/.test(String(result.percent)) && Number(result.percent) <= 100 ? number(Number(result.percent)) + '%' : '';
    const change = percent ? l('A ' + percent + ' reduction', percent + ':n vähennys', 'En minskning med ' + percent) : l('This reduction', 'Tämä vähennys', 'Denna minskning');
    answer = [integer(value) ? l(
      change + ' in ' + category(result.category) + ' would free up about ' + amount(value) + ' per month, using ' + amount(base) + ' of adjustable spending ' + during(period) + '.',
      change + ' luokassa ' + category(result.category) + ' vapauttaisi noin ' + amount(value) + ' kuukaudessa. Muokattava kulutuspohja on ' + amount(base) + ' ' + during(period) + '.',
      change + ' för ' + category(result.category) + ' skulle frigöra cirka ' + amount(value) + ' per månad, utifrån ' + amount(base) + ' i justerbara utgifter ' + during(period) + '.')
      : l('A monthly saving estimate is unavailable for this change ' + during(period) + '.',
        'Tälle muutokselle ei ole kuukausisäästöarviota ' + during(period) + '.',
        'En uppskattning av månadssparandet saknas för denna ändring ' + during(period) + '.'),
      l('This is an unsaved planning estimate. No money has been moved or saved.',
        'Tämä on tallentamaton suunnitteluarvio. Rahaa ei ole siirretty tai säästetty.',
        'Detta är en osparad planeringsuppskattning. Inga pengar har flyttats eller sparats.')];
    if (integer(base) && integer(result.actual_total_cents) && base !== result.actual_total_cents) answer[0] += ' ' + l(
      'The full recorded spending was ' + amount(result.actual_total_cents) + '.',
      'Kirjatut menot olivat yhteensä ' + amount(result.actual_total_cents) + '.',
      'De totala registrerade utgifterna var ' + amount(result.actual_total_cents) + '.');
  } else if (response.tool_kind === 'three_basket_profile') {
    answer = [l(
      'Your recorded spending was ' + amount(result.total_consumption_cents) + ' ' + during(period) + '.',
      'Kirjatut menosi olivat ' + amount(result.total_consumption_cents) + ' ' + during(period) + '.',
      'Dina registrerade utgifter var ' + amount(result.total_consumption_cents) + ' ' + during(period) + '.')];
    const baskets = (result.baskets || []).filter(row => integer(row.amount_cents)).map(row => amount(row.amount_cents) + ' (' + flow(row.role) + ')');
    if (baskets.length) answer[0] += ' ' + l('The breakdown is ', 'Jakauma on ', 'Fördelningen är ') + list(baskets) + '.';
    answer.push(l('These groups describe payments, not a personality or a spender score.',
      'Ryhmät kuvaavat maksuja, eivät persoonallisuuttasi tai rahankäyttäjän pisteytystä.',
      'Grupperna beskriver betalningar, inte din personlighet eller ett betyg på dig som spenderare.'));
  } else if (response.tool_kind === 'safe_to_spend') {
    if (result.available === false || !integer(result.safe_to_spend_cents)) answer = [l(
      'There is not enough usable account history to give a safe-to-spend estimate.',
      'Käyttökelpoista tilihistoriaa ei ole riittävästi turvallisen käyttövaran arvioimiseen.',
      'Det finns inte tillräcklig användbar kontohistorik för att uppskatta ett tryggt belopp att spendera.')];
    else {
      const reference = date(result.reference_date || result.as_of), end = date(result.horizon_end);
      const horizon = integer(result.horizon_days) ? l('the next ' + number(result.horizon_days) + ' days', 'seuraaville ' + number(result.horizon_days) + ' päivälle', 'de följande ' + number(result.horizon_days) + ' dagarna') : l('the stated period', 'ilmoitetulle jaksolle', 'den angivna perioden');
      answer = [result.safe_to_spend_cents === 0 ? l(
        'There is no estimated room for extra spending for ' + horizon + (end ? ', through ' + end : '') + (reference ? ', using ' + reference + ' as the reference date' : '') + '.',
        'Tilillä ei ole arvioitua käyttövaraa ylimääräiseen kulutukseen ' + horizon + (end ? ', ' + end + ' asti' : '') + (reference ? '. Viitepäivä on ' + reference : '') + '.',
        'Det finns inget uppskattat utrymme för extra utgifter för ' + horizon + (end ? ', till ' + end : '') + (reference ? ', med ' + reference + ' som referensdag' : '') + '.')
        : l(
        'The spending estimate is ' + amount(result.safe_to_spend_cents) + ' for ' + horizon + (end ? ', through ' + end : '') + (reference ? ', using ' + reference + ' as the reference date' : '') + '.',
        'Arvioitu käyttövara on ' + amount(result.safe_to_spend_cents) + ' ' + horizon + (end ? ', ' + end + ' asti' : '') + (reference ? '. Viitepäivä on ' + reference : '') + '.',
        'Det uppskattade beloppet att spendera är ' + amount(result.safe_to_spend_cents) + ' för ' + horizon + (end ? ', till ' + end : '') + (reference ? ', med ' + reference + ' som referensdag' : '') + '.')];
      const protectedAmounts = [
        integer(result.reserve_floor_cents) ? amount(result.reserve_floor_cents) + ' ' + (result.reserve_floor_source === 'demo_default' ? l('demo reserve', 'demon vararaha', 'demobuffert') : l('reserve', 'vararaha', 'buffert')) : '',
        integer(result.scheduled_outflows_cents) ? amount(result.scheduled_outflows_cents) + ' ' + l('expected outflows', 'odotetut menot', 'väntade utflöden') : '',
        integer(result.historical_flexible_buffer_cents) ? amount(result.historical_flexible_buffer_cents) + ' ' + l('everyday-spending allowance', 'arjen kulutusvara', 'utrymme för vardagsutgifter') : '',
      ].filter(Boolean);
      if (protectedAmounts.length) answer[0] += ' ' + l('The calculation deducts ', 'Laskelma vähentää nämä erät: ', 'Beräkningen drar av ') + list(protectedAmounts) + '.';
      answer.push(l('This is a planning estimate, not a guarantee. New bills, goal allocations and unsaved tax plans may reduce it; expected income is excluded until it arrives.',
        'Tämä on suunnitteluarvio, ei takuu. Uudet laskut, tavoitteisiin varatut summat ja tallentamattomat verosuunnitelmat voivat pienentää sitä. Odotettuja tuloja ei lasketa ennen niiden saapumista.',
        'Detta är en planeringsuppskattning, inte en garanti. Nya räkningar, målavsättningar och osparade skatteplaner kan minska beloppet; väntade inkomster räknas först när de kommer in.'));
    }
  } else if (response.tool_kind === 'cashflow_forecast') {
    const points = (result.projected || []).filter(row => integer(row.balance_cents));
    if (!points.length) answer = [l('A balance forecast is unavailable from the returned records.',
      'Palautetuista tiedoista ei ole saatavilla saldoennustetta.',
      'En saldoprognos saknas för de returnerade uppgifterna.')];
    else {
      const end = points.at(-1), low = points.reduce((a, b) => a.balance_cents <= b.balance_cents ? a : b);
      const reference = date(result.as_of);
      answer = [l(
        'The 30-day balance preview' + (reference ? ' from ' + reference : '') + ' ends at an estimated ' + amount(end.balance_cents) + (end.date ? ' on ' + date(end.date) : '') + '. The lowest estimated balance is ' + amount(low.balance_cents) + (low.date ? ' on ' + date(low.date) : '') + '.',
        '30 päivän saldoarvion' + (reference ? ' viitepäivä on ' + reference + ' ja' : '') + ' loppusaldo on arviolta ' + amount(end.balance_cents) + (end.date ? ' päivänä ' + date(end.date) : '') + '. Pienin arvioitu saldo on ' + amount(low.balance_cents) + (low.date ? ' päivänä ' + date(low.date) : '') + '.',
        '30-dagarsprognosen' + (reference ? ' från ' + reference : '') + ' slutar på uppskattningsvis ' + amount(end.balance_cents) + (end.date ? ' den ' + date(end.date) : '') + '. Det lägsta uppskattade saldot är ' + amount(low.balance_cents) + (low.date ? ' den ' + date(low.date) : '') + '.'),
      l('This uses past income and spending patterns; future bills and income may differ. Any displayed range reflects past variation, not a probability.',
        'Arvio käyttää aiempia tulo- ja menomalleja. Tulevat laskut ja tulot voivat poiketa niistä. Mahdollinen vaihteluväli kuvaa aiempaa vaihtelua, ei todennäköisyyttä.',
        'Detta bygger på tidigare inkomst- och utgiftsmönster; framtida räkningar och inkomster kan skilja sig. Ett visat intervall speglar tidigare variation, inte en sannolikhet.')];
    }
  } else if (response.tool_kind === 'investment_cashflow') {
    const window = result.start_month && result.end_month ? month(result.start_month) + '–' + month(result.end_month) : period;
    answer = [l(
      'Recorded transfers into investments totaled ' + amount(result.total_contributions_cents) + ', and withdrawals totaled ' + amount(result.withdrawals_cents) + ' ' + during(window) + '.',
      'Kirjattuja sijoitussiirtoja oli ' + amount(result.total_contributions_cents) + ' ja nostoja ' + amount(result.withdrawals_cents) + ' ' + during(window) + '.',
      'Registrerade överföringar till investeringar uppgick till ' + amount(result.total_contributions_cents) + ' och uttag till ' + amount(result.withdrawals_cents) + ' ' + during(window) + '.')];
    if (integer(result.contribution_months) && integer(result.period_months)) answer[0] += ' ' + l(
      'You contributed in ' + number(result.contribution_months) + ' of ' + number(result.period_months) + ' observed months.',
      'Sijoitussiirtoja oli ' + number(result.contribution_months) + ' kuukaudessa ' + number(result.period_months) + ' havaitusta kuukaudesta.',
      'Du gjorde insättningar under ' + number(result.contribution_months) + ' av ' + number(result.period_months) + ' observerade månader.');
    answer.push(l('These are account transfers, not holdings, portfolio values or investment returns.',
      'Nämä ovat tilisiirtoja, eivät omistuksia, salkun arvoja tai sijoitustuottoja.',
      'Detta är kontoöverföringar, inte innehav, portföljvärden eller avkastning.'));
    if (result.coverage_limited) answer[1] += ' ' + l('Only the available part of the requested period is covered.',
      'Pyydetystä ajanjaksosta mukana on vain käytettävissä oleva osa.',
      'Bara den tillgängliga delen av den begärda perioden ingår.');
  } else if (response.tool_kind === 'vat_estimate') {
    if (!integer(result.estimated_vat_cents) || (result.gross_spending_cents > 0 && result.covered_spending_cents === 0)) answer = [l(
      'A VAT estimate is unavailable for these recorded purchases ' + during(period) + '.',
      'Näille kirjatuille ostoksille ei ole saatavilla ALV-arviota ' + during(period) + '.',
      'En momsuppskattning saknas för dessa registrerade köp ' + during(period) + '.')];
    else if (result.gross_spending_cents === 0) answer = [l(
      'No qualifying purchases were recorded ' + during(period) + ', so there is no VAT estimate to report.',
      'Soveltuvia ostoksia ei kirjattu ' + during(period) + ', joten ALV-arviota ei ole raportoitavana.',
      'Inga relevanta köp registrerades ' + during(period) + ', så det finns ingen momsuppskattning att redovisa.')];
    else {
      answer = [l(
        'An estimated ' + amount(result.estimated_vat_cents) + ' of VAT was already included in your recorded purchase prices ' + during(period) + '.',
        'Kirjattuihin ostohintoihisi sisältyi arviolta ' + amount(result.estimated_vat_cents) + ' ALV:tä ' + during(period) + '.',
        'Uppskattningsvis ' + amount(result.estimated_vat_cents) + ' i moms ingick redan i dina registrerade inköpspriser ' + during(period) + '.')];
      if (integer(result.gross_spending_cents)) answer[0] += ' ' + l('Those purchases totaled ' + amount(result.gross_spending_cents) + '.',
        'Ostosten yhteissumma oli ' + amount(result.gross_spending_cents) + '.',
        'Köpen uppgick till ' + amount(result.gross_spending_cents) + '.');
    }
    let limitation = l('Mixed purchases and missing rate mappings limit this estimate. It is not an additional payment or a personal tax liability.',
      'Sekalaiset ostokset ja puuttuvat verokantatiedot rajoittavat arviota. Se ei ole lisämaksu tai henkilökohtainen verovelka.',
      'Blandade köp och saknade momssatsmappningar begränsar uppskattningen. Det är ingen extra betalning eller personlig skatteskuld.');
    if (integer(result.coverage_basis_points)) limitation = l(
      'The mapping covers ' + number(result.coverage_basis_points / 100) + '% of recorded purchase spending; that is coverage, not an accuracy score. ',
      'Verokanta on arvioitu ' + number(result.coverage_basis_points / 100) + ' prosentille kirjatuista ostosmenoista. Tämä kuvaa kattavuutta, ei tarkkuutta. ',
      'Mappningen täcker ' + number(result.coverage_basis_points / 100) + '% av registrerade inköpsutgifter; det är täckning, inte ett mått på noggrannhet. ') + limitation;
    answer.push(limitation);
  } else if (response.tool_kind === 'observed_tax_evidence') {
    if (result.available === false) answer = [l(
      'I found no explicit tax records ' + during(period) + '. This does not mean that no tax was paid.',
      'Nimenomaisia verotietoja ei löytynyt ' + during(period) + '. Tämä ei tarkoita, ettei veroa olisi maksettu.',
      'Jag hittade inga uttryckliga skatteuppgifter ' + during(period) + '. Det betyder inte att ingen skatt betalades.')];
    else answer = [l(
      'Explicit tax payments totaled ' + amount(result.observed_tax_paid_cents) + ' and recorded tax refunds totaled ' + amount(result.observed_tax_refund_cents) + ' ' + during(period) + '.',
      'Nimenomaisia veromaksuja oli ' + amount(result.observed_tax_paid_cents) + ' ja kirjattuja veronpalautuksia ' + amount(result.observed_tax_refund_cents) + ' ' + during(period) + '.',
      'Uttryckliga skattebetalningar uppgick till ' + amount(result.observed_tax_paid_cents) + ' och registrerade skatteåterbetalningar till ' + amount(result.observed_tax_refund_cents) + ' ' + during(period) + '.')];
    answer.push(l('This covers only explicitly identified records; it does not establish your complete tax liability.',
      'Mukana ovat vain nimenomaisesti tunnistetut tiedot. Niistä ei voi päätellä koko verovelkaasi.',
      'Detta omfattar bara uttryckligen identifierade uppgifter; det fastställer inte hela din skatteskuld.'));
  } else if (response.tool_kind === 'home_financing_history') {
    if (!result.available) answer = [l(
      'No linked home-financing history is available for this account. You can still explore a home savings wish.',
      'Tälle tilille ei ole yhdistettyä asuntorahoitushistoriaa. Voit silti pohtia kotisäästötoivetta.',
      'Ingen kopplad bostadsfinansieringshistorik finns för kontot. Du kan ändå utforska en sparönskan för ett hem.')];
    else {
      const decision = result.recorded_outcome?.decision;
      answer = [decision === 'approved' ? l('The linked historical mortgage application was recorded as approved.',
        'Yhdistetty historiallinen asuntolainahakemus on kirjattu hyväksytyksi.',
        'Den kopplade historiska bolåneansökan registrerades som godkänd.')
        : decision === 'rejected' ? l('The linked historical mortgage application was recorded as declined.',
          'Yhdistetty historiallinen asuntolainahakemus on kirjattu hylätyksi.',
          'Den kopplade historiska bolåneansökan registrerades som avslagen.')
        : l('A linked historical mortgage application is available, but its outcome is unavailable.',
          'Yhdistetty historiallinen asuntolainahakemus on saatavilla, mutta sen päätös puuttuu.',
          'En kopplad historisk bolåneansökan finns, men beslutet saknas.')];
      if (integer(result.requested_loan_cents)) answer[0] += ' ' + l(
        'The requested loan was ' + amount(result.requested_loan_cents) + '.',
        'Haettu lainasumma oli ' + amount(result.requested_loan_cents) + '.',
        'Det ansökta lånebeloppet var ' + amount(result.requested_loan_cents) + '.');
      if (integer(result.equity_cents)) answer[0] += ' ' + l(
        'The equity recorded then was ' + amount(result.equity_cents) + '.',
        'Tuolloin kirjattu omarahoitus oli ' + amount(result.equity_cents) + '.',
        'Den då registrerade egna insatsen var ' + amount(result.equity_cents) + '.');
      answer.push(l('These past records do not establish a current mortgage, available savings, household finances or a new lending decision.',
        'Nämä aiemmat tiedot eivät osoita nykyistä asuntolainaa, käytettävissä olevia säästöjä, kotitalouden taloutta tai uutta lainapäätöstä.',
        'Dessa tidigare uppgifter fastställer inte ett nuvarande bolån, tillgängligt sparande, hushållets ekonomi eller ett nytt lånebeslut.'));
    }
  } else return supplied;

  if (response.source === 'gemini') {
    const existing = answer.map(key).join(' ');
    const meaningful = paragraphs((response.explanation_blocks || []).map(block => block?.text))
      .filter(text => !genericIntros.has(key(text)) && !existing.includes(key(text)));
    if (meaningful.length) answer.push(meaningful.join(' '));
  }
  return paragraphs(answer);
}
