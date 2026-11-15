/**
 * Home as the Payday Plan (V4 lane H).
 *
 * Top to bottom: plan hero ("€X a day until payday" + why), one coach insight with up to two
 * actions, this month (in / spent / left over), the surprise buffer, goals and plans, a small
 * personalise row, and seasonal extras. Pure helpers are exported for tests; createHome() wires
 * them to the app. All amounts are integer cents. All text exists in EN, FI and SV.
 */

import { updateDraftPreview } from './draft-card.js';
import { emptyStateHTML, emptyText } from './empty-states.js';

const LOCALES = ['en', 'fi', 'sv'];

const COPY = {
  'title': ['Your payday plan', 'Palkkapäivän suunnitelma', 'Din lönedagsplan'],
  'eyebrow': ['Payday plan', 'Palkkapäivän suunnitelma', 'Lönedagsplan'],
  'canUse': ['You can use about', 'Voit käyttää noin', 'Du kan använda ungefär'],
  'perDay': ['a day for food, getting around and fun', 'päivässä ruokaan, liikkumiseen ja muuhun', 'om dagen för mat, resor och nöjen'],
  'perDayFallback': ['a day for the next {days} days', 'päivässä seuraavat {days} päivää', 'om dagen de kommande {days} dagarna'],
  'paydayIn': ['Payday in {days} days · {date}', 'Palkkapäivään {days} päivää · {date}', 'Lönedag om {days} dagar · {date}'],
  'paydayTomorrow': ['Payday tomorrow · {date}', 'Palkkapäivä huomenna · {date}', 'Lönedag i morgon · {date}'],
  'noPayday': ['No regular salary found yet, so this plan covers {days} days.', 'Säännöllistä palkkaa ei vielä löytynyt, joten suunnitelma kattaa {days} päivää.', 'Ingen regelbunden lön hittades än, så planen gäller {days} dagar.'],
  'balance': ['In your account', 'Tililläsi', 'På ditt konto'],
  'seg.held': ['Held back', 'Varattu', 'Avsatt'],
  'seg.cushion': ['Safety cushion', 'Turvatyyny', 'Säkerhetsmarginal'],
  'seg.surprise': ['Surprise buffer', 'Yllätyspuskuri', 'Buffert för oväntat'],
  'seg.extraSteady': ['Not needed before payday', 'Ei tarvita ennen palkkapäivää', 'Behövs inte före lönedagen'],
  'seg.sum': ['{everyday} + {free} = {total} → about {perDay} a day', '{everyday} + {free} = {total} → noin {perDay} päivässä', '{everyday} + {free} = {total} → ungefär {perDay} om dagen'],
  'seg.covered': ['In your account', 'Tililläsi', 'På ditt konto'],
  'seg.missing': ['Missing for bills', 'Laskuista puuttuu', 'Saknas för räkningar'],
  'seg.bills': ['Bills before payday', 'Laskut ennen palkkapäivää', 'Räkningar före lönedagen'],
  'seg.afterBills': ['Left after bills', 'Jää laskujen jälkeen', 'Kvar efter räkningar'],
  'seg.everyday': ['Everyday basics', 'Ruoka ja liikkuminen', 'Mat och resor'],
  'seg.free': ['Free to spend', 'Käytettävissä', 'Fritt att använda'],
  'seg.extra': ['Could be saved', 'Voisi säästää', 'Kan sparas'],
  'why': ['Why this number?', 'Miksi tämä summa?', 'Varför det här beloppet?'],
  'why.balance': ['In your account now', 'Tililläsi nyt', 'På ditt konto nu'],
  'why.reserve': ['Safety cushion, kept untouched', 'Turvatyyny, johon ei kosketa', 'Säkerhetsmarginal som lämnas orörd'],
  'why.reserveSteady': ['Safety cushion: a month of must-pays (steady mode)', 'Turvatyyny: kuukauden välttämättömät menot (rauhallinen tahti)', 'Säkerhetsmarginal: en månads nödvändiga utgifter (lugnt tempo)'],
  'why.buffer': ['Surprise buffer, this payday', 'Yllätyspuskuri tälle palkkakaudelle', 'Buffert för oväntat, den här perioden'],
  'why.bufferPlan': ['Surprise buffer, your plan', 'Yllätyspuskuri, oma suunnitelmasi', 'Buffert för oväntat, din plan'],
  'why.daily': ['Money for daily life until payday', 'Rahaa arkeen palkkapäivään asti', 'Pengar till vardagen fram till lönedagen'],
  'why.dailyParts': ['Everyday basics {everyday} + free to spend {free}', 'Arjen perusmenot {everyday} + käytettävissä {free}', 'Vardagsutgifter {everyday} + fritt att använda {free}'],
  'why.extraSteady': ['More than you need before payday, kept in your account', 'Enemmän kuin tarvitset ennen palkkapäivää, pysyy tililläsi', 'Mer än du behöver före lönedagen, stannar på kontot'],
  'why.short': ['Short for bills before payday', 'Laskuista puuttuu ennen palkkapäivää', 'Saknas för räkningar före lönedagen'],
  'why.left': ['Left after bills', 'Jää laskujen jälkeen', 'Kvar efter räkningar'],
  'why.notKept': ['Can’t be kept this time', 'Ei mahdu tällä kertaa', 'Ryms inte den här gången'],
  'why.notFull': ['Not fully covered this time', 'Ei katettu kokonaan tällä kertaa', 'Inte helt täckt den här gången'],
  'why.everyday': ['Everyday basics until payday', 'Ruoka ja liikkuminen palkkapäivään asti', 'Mat och resor fram till lönedagen'],
  'why.extra': ['More than you usually need: could be saved', 'Enemmän kuin yleensä tarvitset: voisi säästää', 'Mer än du brukar behöva: kan sparas'],
  'why.free': ['Free to spend until payday', 'Käytettävissä palkkapäivään asti', 'Fritt att använda fram till lönedagen'],
  'why.perDay': ['{amount} over {days} days is about {perDay} a day.', 'Ruokaan, liikkumiseen ja vapaaseen käyttöön jää yhteensä {amount}. Kun se jaetaan {days} päivälle, saat {perDay} päivässä.', 'Till mat, resor och fritt att använda finns sammanlagt {amount}. Fördelat på {days} {days|dag|dagar} blir det {perDay} om dagen.'],
  'perDayTotal': ['{total} in total until payday', 'Yhteensä {total} palkkapäivään asti', 'Totalt {total} fram till lönedagen'],
  'short.lead': ['Before payday you are short', 'Ennen palkkapäivää rahaa puuttuu', 'Före lönedagen saknas'],
  'short.unit': ['for bills that are due', 'erääntyvistä laskuista', 'för räkningar som förfaller'],
  'short.bills': ['{bills} is {gap} more than the {balance} in your account.', '{bills} on {gap} enemmän kuin tililläsi oleva {balance}.', '{bills} är {gap} mer än de {balance} som finns på kontot.'],
  'short.billsMany': ['Bills before payday ({bills}) are {gap} more than the {balance} in your account.', 'Laskut ennen palkkapäivää ({bills}) ovat {gap} enemmän kuin tililläsi oleva {balance}.', 'Räkningarna före lönedagen ({bills}) är {gap} mer än de {balance} som finns på kontot.'],
  'short.cushion': ['Your {cushion} safety cushion can’t be kept this time.', 'Turvatyynyäsi ({cushion}) ei voi pitää tällä kertaa.', 'Din säkerhetsmarginal på {cushion} ryms inte den här gången.'],
  'short.cushionBuffer': ['Your {cushion} safety cushion and {buffer} surprise buffer can’t be kept this time.', 'Turvatyynyäsi ({cushion}) ja yllätyspuskuria ({buffer}) ei voi pitää tällä kertaa.', 'Din säkerhetsmarginal på {cushion} och bufferten för oväntat på {buffer} ryms inte den här gången.'],
  'left.lead': ['Left after bills until payday', 'Laskujen jälkeen jää palkkapäivään asti', 'Kvar efter räkningarna fram till lönedagen'],
  'left.unit': ['Spend it on basics only', 'Käytä se vain välttämättömään', 'Använd dem bara till det nödvändiga'],
  'left.covered': ['Your bills before payday are covered.', 'Laskusi ennen palkkapäivää on katettu.', 'Dina räkningar före lönedagen är täckta.'],
  'left.cushion': ['The {left} left is less than your {cushion} safety cushion, so nothing is counted as free to spend this time.', 'Jäljelle jäävä {left} on vähemmän kuin turvatyynysi {cushion}, joten vapaata käyttörahaa ei tällä kertaa jää.', 'De {left} som blir kvar är mindre än din säkerhetsmarginal på {cushion}, så inget räknas som fritt att använda den här gången.'],
  'left.steady': ['Steady mode keeps a month of must-pays ({cushion}) as your safety cushion. The {left} left doesn’t reach it yet, so nothing is counted as free to spend.', 'Rauhallinen tahti pitää kuukauden välttämättömät menot ({cushion}) turvatyynynä. Jäljelle jäävä {left} ei vielä riitä siihen, joten vapaata käyttörahaa ei lasketa.', 'Lugnt tempo håller en månads nödvändiga utgifter ({cushion}) som säkerhetsmarginal. De {left} som blir kvar räcker inte än, så inget räknas som fritt att använda.'],
  'why.note': ['Your next salary is counted only when it arrives. Nothing moves from your account.', 'Seuraava palkka lasketaan mukaan vasta, kun se on tilillä. Tililtäsi ei siirry rahaa.', 'Nästa lön räknas först när den har kommit. Inga pengar flyttas från ditt konto.'],
  'why.held': ['Held back for what is due before payday', 'Varattu ennen palkkapäivää erääntyviin', 'Avsatt för det som förfaller före lönedagen'],
  'kind.saving': ['Your planned saving', 'Suunnittelemasi säästö', 'Ditt planerade sparande'],
  'kind.savingPct': ['Your planned saving, {pct} of salary', 'Suunnittelemasi säästö, {pct} palkasta', 'Ditt planerade sparande, {pct} av lönen'],
  'kind.tax': ['Tax set-aside', 'Verovaraus', 'Skatteavsättning'],
  'kind.loan': ['Loan payment', 'Lainanlyhennys', 'Låneamortering'],
  'told': ['You told me', 'Kerroit minulle', 'Du berättade'],
  'steady': ['Steady mode is on because you told me about {event}. A month of must-pays is kept aside.', 'Rauhallinen tahti on päällä, koska kerroit tilanteestasi ({event}). Kuukauden välttämättömät menot pidetään sivussa.', 'Lugnt tempo är på eftersom du berättade om {event}. En månads nödvändiga utgifter hålls undan.'],
  'event.job_loss': ['losing your job', 'työpaikan menetys', 'att du har förlorat jobbet'],
  'event.income_drop': ['a drop in income', 'tulojen lasku', 'att inkomsten har minskat'],
  'event.large_loss': ['a large unexpected cost', 'suuri yllättävä meno', 'en stor oväntad kostnad'],
  'event.other': ['a change in your life', 'elämänmuutos', 'en förändring i ditt liv'],
  'loading': ['Working out your plan…', 'Lasketaan suunnitelmaasi…', 'Räknar ut din plan…'],
  'unavailable': ['Your plan is not available right now. Please try again in a moment.', 'Suunnitelmasi ei ole juuri nyt saatavilla. Yritä hetken päästä uudelleen.', 'Din plan är inte tillgänglig just nu. Försök igen om en stund.'],
  'insight.eyebrow': ['From your coach', 'Valmentajaltasi', 'Från din coach'],
  'insight.buffer': ['Surprise costs like the dentist or a repair came to about {amount} a month for you last year. A little set aside each payday means the next one won’t hurt.', 'Viime vuonna yllättäviin menoihin, kuten hammaslääkäriin ja korjauksiin, kului noin {amount} kuukaudessa. Kun laitat joka palkkapäivä pienen summan sivuun, seuraava yllätys ei kirpaise.', 'Förra året lade du i snitt cirka {amount} i månaden på oväntade kostnader som tandläkare och reparationer. Lägger du undan lite varje lönedag svider nästa inte lika mycket.'],
  'insight.extra': ['You have {amount} more than you usually need before payday. Moving it to savings keeps it from slipping into everyday spending.', 'Sinulla on {amount} enemmän kuin tavallisesti tarvitset ennen palkkapäivää. Säästöön siirrettynä se ei huku arkeen.', 'Du har {amount} mer än du brukar behöva före lönedagen. Flyttar du det till sparande försvinner det inte i vardagen.'],
  'insight.shortfall': ['Money is tight before payday. Let’s look together at which bills could wait or be split, and what to do first.', 'Rahaa on niukasti ennen palkkapäivää. Katsotaan yhdessä, mitkä laskut voisivat odottaa tai jakautua osiin ja mitä tehdä ensin.', 'Pengarna är knappa före lönedagen. Vi tittar tillsammans på vilka räkningar som kan vänta eller delas upp, och vad du gör först.'],
  'insight.steady': ['Your safety cushion comes first right now: a month of must-pays is kept aside before anything else. I won’t push saving goals until things settle.', 'Turvatyyny on nyt etusijalla: kuukauden välttämättömät menot pidetään sivussa ennen kaikkea muuta. En ehdota säästötavoitteita, ennen kuin tilanne tasaantuu.', 'Din säkerhetsmarginal kommer först just nu: en månads nödvändiga utgifter hålls undan före allt annat. Jag föreslår inga sparmål förrän läget har lugnat sig.'],
  'insight.topCategory': ['{category} was your biggest everyday extra this month, {amount}.', '{category} oli tämän kuun suurin arjen lisämeno, {amount}.', '{category} var månadens största vardagsextra, {amount}.'],
  'chip.category': ['Look at {category}', 'Tarkastele: {category}', 'Titta på {category}'],
  'q.category': ['How much did I spend on {category} this month, and how could I spend less?', 'Paljonko käytin tässä kuussa kohteeseen {category}, ja miten voisin käyttää vähemmän?', 'Hur mycket spenderade jag på {category} den här månaden, och hur kan jag spendera mindre?'],
  'insight.spentLess': ['You spent {amount} less than in {month}. That is room for your plan.', 'Käytit {amount} vähemmän kuin {month}. Se on tilaa suunnitelmallesi.', 'Du spenderade {amount} mindre än i {month}. Det ger utrymme för din plan.'],
  'insight.spentMore': ['You spent {amount} more than in {month}. Want to see where it went?', 'Käytit {amount} enemmän kuin {month}. Haluatko nähdä, mihin rahat menivät?', 'Du spenderade {amount} mer än i {month}. Vill du se vart pengarna gick?'],
  'insight.calm': ['Your bills before payday are covered. Spending about {amount} a day keeps you on plan.', 'Ennen palkkapäivää erääntyvät laskut on katettu. Noin {amount} päivässä pitää sinut suunnitelmassa.', 'Räkningarna före lönedagen är täckta. Ungefär {amount} om dagen håller dig på plan.'],
  'insight.savingTold': ['You told me you want to save {pct} of your salary, so that is held back first.', 'Kerroit haluavasi säästää {pct} palkastasi, joten se varataan ensin.', 'Du berättade att du vill spara {pct} av lönen, så det avsätts först.'],
  'chip.bufferCard': ['See the surprise buffer', 'Katso yllätyspuskuri', 'Se bufferten för oväntat'],
  'chip.where': ['See where it goes', 'Katso, mihin rahat menevät', 'Se vart pengarna går'],
  'chip.goal': ['Make it a goal', 'Tee siitä tavoite', 'Gör det till ett mål'],
  'chip.ask': ['Ask the coach', 'Kysy valmentajalta', 'Fråga coachen'],
  'chip.due': ['See what is due', 'Katso, mitä erääntyy', 'Se vad som förfaller'],
  'chip.situation': ['Update my situation', 'Päivitä tilanteeni', 'Uppdatera min situation'],
  'q.shortfall': ['My bills before payday are more than I have. What can I do?', 'Laskuni ennen palkkapäivää ovat enemmän kuin minulla on rahaa. Mitä voin tehdä?', 'Mina räkningar före lönedagen är mer än jag har. Vad kan jag göra?'],
  'q.steady': ['What should I focus on while money is tight?', 'Mihin minun kannattaa keskittyä, kun rahaa on vähän?', 'Vad ska jag fokusera på när pengarna är knappa?'],
  'q.save': ['How could I save more?', 'Miten voisin säästää enemmän?', 'Hur kan jag spara mer?'],
  'q.safe': ['What can I safely spend until payday?', 'Paljonko voin turvallisesti käyttää palkkapäivään asti?', 'Hur mycket kan jag tryggt spendera fram till lönedagen?'],
  'month.title': ['This month', 'Tämä kuukausi', 'Den här månaden'],
  'month.choose': ['Choose month', 'Valitse kuukausi', 'Välj månad'],
  'month.in': ['Money in', 'Tulot', 'Pengar in'],
  'month.out': ['Spent', 'Menot', 'Utgifter'],
  'month.left': ['Left over', 'Jäi yli', 'Blev över'],
  'month.vs': ['{amount} vs {month}', '{amount} viime kuusta', '{amount} jfr {month}'],
  'month.same': ['Same as {month}', 'Sama kuin viime kuussa', 'Samma som {month}'],
  'month.empty': ['No activity recorded for this month.', 'Tälle kuukaudelle ei ole kirjattu tapahtumia.', 'Ingen aktivitet registrerad för den här månaden.'],
  'buffer.title': ['Surprise buffer', 'Yllätyspuskuri', 'Buffert för oväntat'],
  'buffer.help': ['For costs that always come, just not on schedule: the dentist, the car, a broken washing machine.', 'Menoihin, jotka tulevat aina, mutta eivät aikataulussa: hammaslääkäri, auto, rikkoutunut pesukone.', 'För kostnader som alltid kommer, bara inte enligt schema: tandläkaren, bilen, en trasig tvättmaskin.'],
  'buffer.basis': ['Last 12 months: {total} in surprises, the biggest {largest}.', 'Viimeiset 12 kk: yllätysmenoja {total}, suurin {largest}.', 'Senaste 12 månaderna: {total} i oväntade utgifter, den största {largest}.'],
  'buffer.none': ['No surprise costs in the last year. A small surprise buffer still helps when one comes.', 'Viime vuonna ei ollut yllätysmenoja. Pieni yllätyspuskuri auttaa silti, kun sellainen tulee.', 'Inga oväntade utgifter det senaste året. En liten buffert för oväntat hjälper ändå när något händer.'],
  'buffer.suggest': ['Suggested target', 'Ehdotettu tavoite', 'Föreslaget mål'],
  'buffer.thisPayday': ['This payday’s plan already holds back {amount} for surprise costs, based on your past ones.', 'Tämän palkkakauden suunnitelmassa on jo varattu {amount} yllätysmenoihin aiempien perusteella.', 'Den här periodens plan håller redan undan {amount} för oväntade utgifter, utifrån dina tidigare.'],
  'buffer.heldNow': ['Held back this payday: {amount}', 'Varattu tällä palkkakaudella: {amount}', 'Avsatt den här perioden: {amount}'],
  'buffer.paused': ['Steady mode is on, so I’m not suggesting new saving. Surprise costs are still counted in your payday plan.', 'Rauhallinen tahti on päällä, joten en ehdota uutta säästämistä. Yllätysmenot lasketaan silti mukaan palkkapäivän suunnitelmaan.', 'Lugnt tempo är på, så jag föreslår inget nytt sparande. Oväntade utgifter räknas ändå med i lönedagsplanen.'],
  'buffer.pausedGoal': ['Paused while steady mode is on. Nothing more is asked of you for now.', 'Tauolla, kun rauhallinen tahti on päällä. Sinulta ei nyt pyydetä enempää.', 'Pausad medan lugnt tempo är på. Inget mer behövs av dig just nu.'],
  'buffer.pace': ['{amount} a month, ready by {date}', '{amount} kuukaudessa, valmis {date}', '{amount} i månaden, klar {date}'],
  'buffer.action': ['Set aside {amount} monthly', 'Varaa {amount} kuukausittain', 'Avsätt {amount} i månaden'],
  'buffer.progress': ['{saved} of {target}', '{saved} / {target}', '{saved} av {target}'],
  'buffer.planned': ['Plan saved: about {amount} each payday until {date}.', 'Suunnitelma tallennettu: noin {amount} joka palkkapäivä {date} asti.', 'Plan sparad: ungefär {amount} varje lönedag till {date}.'],
  'buffer.later': ['Start setting money aside once the bills before payday are covered. Your coach will remind you.', 'Aloita säästäminen, kun palkkapäivää edeltävät laskut on katettu. Valmentaja muistuttaa sinua.', 'Börja lägga undan när räkningarna före lönedagen är täckta. Coachen påminner dig.'],
  'buffer.change': ['Change', 'Muuta', 'Ändra'],
  'draft.title': ['Start your surprise buffer', 'Aloita yllätyspuskuri', 'Starta din buffert för oväntat'],
  'draft.intro': ['This saves a plan: about {amount} set aside on each payday. No money moves from your account.', 'Tämä tallentaa suunnitelman: noin {amount} sivuun joka palkkapäivä. Tililtäsi ei siirry rahaa.', 'Det här sparar en plan: ungefär {amount} undan varje lönedag. Inga pengar flyttas från ditt konto.'],
  'draft.name': ['Name', 'Nimi', 'Namn'],
  'draft.target': ['Target', 'Tavoite', 'Mål'],
  'draft.date': ['Ready by', 'Valmis viimeistään', 'Klar senast'],
  'draft.saved': ['Already set aside', 'Jo sivussa', 'Redan undanlagt'],
  'draft.save': ['Save my plan', 'Tallenna suunnitelma', 'Spara planen'],
  'draft.preview': ['About {amount} a month for {months} months.', 'Noin {amount} kuukaudessa {months} kuukauden ajan.', 'Ungefär {amount} i månaden i {months} {months|månad|månader}.'],
  'draft.defaultName': ['Surprise buffer', 'Yllätyspuskuri', 'Buffert för oväntat'],
  'draft.saved.notice': ['Your surprise buffer plan is saved. No money was moved.', 'Yllätyspuskurin suunnitelma on tallennettu. Rahaa ei siirretty.', 'Planen för bufferten för oväntat är sparad. Inga pengar flyttades.'],
  'goals.title': ['Goals and plans', 'Tavoitteet ja suunnitelmat', 'Mål och planer'],
  'goals.all': ['All goals', 'Kaikki tavoitteet', 'Alla mål'],
  'goals.line': ['{saved} of {target} · by {date}', '{saved} / {target} · {date} mennessä', '{saved} av {target} · senast {date}'],
  'goals.monthly': ['{amount} a month', '{amount}/kk', '{amount}/mån'],
  'goals.wish': ['A wish to explore', 'Tutkittava toive', 'En önskan att utforska'],
  'goals.empty': ['Nothing planned yet. A wish is enough to start.', 'Ei vielä suunnitelmia. Toive riittää alkuun.', 'Inget planerat än. En önskan räcker för att börja.'],
  'goals.start': ['Start a goal', 'Aloita tavoite', 'Starta ett mål'],
  'plan.mortgage': ['Mortgage plan', 'Asuntolainasuunnitelma', 'Bolåneplan'],
  'plan.tax': ['Tax plan', 'Verosuunnitelma', 'Skatteplan'],
  'plan.buffer': ['Surprise buffer', 'Yllätyspuskuri', 'Buffert för oväntat'],
  'plan.held': ['About {amount} a month held back', 'Noin {amount} kuukaudessa varattu', 'Ungefär {amount} i månaden avsatt'],
  'plan.monthly': ['About {amount} a month', 'Noin {amount} kuukaudessa', 'Ungefär {amount} i månaden'],
  'plan.on': ['On', 'Päällä', 'På'],
  'goal.savingsName': ['Savings', 'Säästöt', 'Sparande'],
  'personal.title': ['Make the plan yours', 'Tee suunnitelmasta omasi', 'Gör planen till din'],
  'personal.help': ['Tell the coach a little about you, and the plan fits your life.', 'Kerro valmentajalle vähän itsestäsi, niin suunnitelma sopii elämääsi.', 'Berätta lite om dig för coachen, så passar planen ditt liv.'],
  'personal.start': ['Tell the coach about you', 'Kerro itsestäsi valmentajalle', 'Berätta om dig för coachen'],
  'personal.known1': ['Your coach knows 1 thing you told it', 'Valmentajasi tietää yhden asian, jonka kerroit', 'Din coach vet 1 sak du har berättat'],
  'personal.known': ['Your coach knows {count} things you told it', 'Valmentajasi tietää {count} asiaa, jotka kerroit', 'Din coach vet {count} saker du har berättat'],
  'personal.review': ['Review', 'Tarkista', 'Granska'],
  'personal.prefs': ['Preferences', 'Asetukset', 'Inställningar'],
  'seasonal': ['Also this season', 'Myös nyt ajankohtaista', 'Också aktuellt nu'],
};

export const HOME_MESSAGES = Object.freeze(Object.fromEntries(LOCALES.map((locale, index) => [
  locale, Object.freeze(Object.fromEntries(Object.entries(COPY).map(([key, values]) => [key, values[index]])))])));

const lang = locale => (LOCALES.includes(locale) ? locale : 'en');
/** Localized Home copy with {name} placeholders. */
export function hm(locale, key, values = {}) {
  const template = HOME_MESSAGES[lang(locale)][key] ?? HOME_MESSAGES.en[key] ?? key;
  // {days|one|other} picks the singular after exactly 1 (FI päivä/päivää, SV dag/dagar).
  return template.replace(/\{(\w+)\|([^|{}]*)\|([^{}]*)\}/g, (_, name, one, other) => (Number(values[name]) === 1 ? one : other))
    .replace(/\{(\w+)\}/g, (_, name) => (values[name] ?? '{' + name + '}'));
}
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
const int = value => (Number.isSafeInteger(value) ? value : null);
const pos = value => Math.max(0, int(value) ?? 0);
const TAG = {en: 'en-IE', fi: 'fi-FI', sv: 'sv-FI'};

/** Default formatters for a locale (used by tests and as a fallback). */
export function formatters(locale = 'en') {
  const tag = TAG[lang(locale)];
  const currency = digits => new Intl.NumberFormat(tag, {style: 'currency', currency: 'EUR', minimumFractionDigits: digits, maximumFractionDigits: digits});
  const day = value => new Date(String(value).slice(0, 10) + 'T12:00:00Z');
  const safe = format => value => { const parsed = day(value); return value && !Number.isNaN(parsed.valueOf()) ? format.format(parsed) : ''; };
  return {
    money: cents => (int(cents) === null ? '—' : currency(2).format(cents / 100)),
    whole: cents => (int(cents) === null ? '—' : currency(0).format(Math.round(cents / 100))),
    floor: cents => (int(cents) === null ? '—' : currency(0).format(Math.floor(cents / 100))),
    shortDate: safe(new Intl.DateTimeFormat(tag, {weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC'})),
    date: safe(new Intl.DateTimeFormat(tag, {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'})),
    dayMonth: safe(new Intl.DateTimeFormat(tag, {day: 'numeric', month: 'short', timeZone: 'UTC'})),
    month: month => new Intl.DateTimeFormat(tag, {month: 'long', timeZone: 'UTC'}).format(day(month + '-01')),
    monthYearShort: month => new Intl.DateTimeFormat(tag, {month: 'short', year: 'numeric', timeZone: 'UTC'}).format(day(month + '-01')),
    monthShort: month => new Intl.DateTimeFormat(tag, {month: 'short', timeZone: 'UTC'}).format(day(month + '-01')),
    monthYear: month => new Intl.DateTimeFormat(tag, {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(day(month + '-01')),
    percent: value => new Intl.NumberFormat(tag, {style: 'percent', maximumFractionDigits: 1}).format(Number(value) / 100),
  };
}

const LOAN_TYPES = new Set(['loan_payment', 'loan_repayment', 'mortgage_payment', 'debt_payment']);
const TOLD_SOURCES = new Set(['declared', 'profile', 'you_told_me', 'money_profile']);

/**
 * One plan shape from either API shape.
 * - Lane N `spending_plan`: {balance_cents, next_payday, days_to_payday, held_back[], everyday_cents, buffer_cents,
 *   reserve_floor_cents, free_cents, per_day_cents, extra_cents, ...}
 * - Current `safe_until_payday`: {starting_balance_cents, next_payday, days_until_payday, committed_items[],
 *   planned_saving_cents, reserve_floor_cents, free_cents, safe_to_save_cents, ...}. Its own split is used:
 *   what could move to savings is "could be saved"; the rest of the free money is spendable.
 * Returns null when the input has neither shape. Every amount is nonnegative integer cents, except
 * shortfall (the uncovered gap when bills exceed what is free).
 */
export function normalizePlan(raw) {
  if (!raw || typeof raw !== 'object') return null;
  if (Array.isArray(raw.held_back) && int(raw.balance_cents) !== null) {
    const items = [], cushion = {reserve: 0, buffer: 0};
    let bufferFromPlan = false;
    for (const item of raw.held_back) {
      const amount = pos(item?.amount_cents);
      if (!amount) continue;
      let kind = ['bill', 'loan', 'tax', 'goal', 'buffer', 'reserve'].includes(item.kind) ? item.kind : 'bill';
      // A saved surprise-buffer plan held back by the server (as a goal or a buffer item) is the surprise buffer.
      const fromPlan = (kind === 'goal' || kind === 'buffer') && (item.template === 'buffer' || item.source === 'goal' || item.source === 'plan' || /buffer_(goal|plan)/.test(String(item.key || '')));
      if (kind === 'goal' && fromPlan) kind = 'buffer';
      if (fromPlan) bufferFromPlan = true;
      if (kind === 'reserve' || kind === 'buffer') { cushion[kind] += amount; continue; }
      items.push({kind, label: String(item.label || ''), labels: item.labels && typeof item.labels === 'object' ? item.labels : null, amount, date: item.date || null, told: TOLD_SOURCES.has(item.source) || item.told === true});
    }
    const reserve = Math.max(cushion.reserve, raw.held_back.some(item => item?.kind === 'reserve') ? 0 : pos(raw.reserve_floor_cents));
    const buffer = Math.max(cushion.buffer, raw.held_back.some(item => item?.kind === 'buffer') ? 0 : pos(raw.buffer_cents));
    const free = int(raw.free_cents) ?? 0, extra = Math.min(pos(raw.extra_cents), Math.max(free, 0));
    const spendable = int(raw.spendable_cents) !== null ? pos(raw.spendable_cents) : Math.max(free - extra, 0);
    const days = Math.max(1, int(raw.days_to_payday) ?? int(raw.days_until_payday) ?? 1);
    const heldTotal = items.reduce((sum, item) => sum + item.amount, 0);
    const everyday = pos(raw.everyday_cents);
    const shortfall = int(raw.shortfall_cents) !== null ? pos(raw.shortfall_cents) : Math.max(0, heldTotal + reserve + buffer + everyday - pos(raw.balance_cents));
    return {shape: 'plan', asOf: raw.as_of || null, balance: int(raw.balance_cents), nextPayday: raw.next_payday || null, days,
      paydayKnown: (raw.basis?.payday_source || raw.payday_source || 'detected') !== 'fallback_30_days', items, heldTotal, reserve, buffer,
      everyday, spendable, extra, perDay: int(raw.per_day_cents) ?? Math.floor((spendable + everyday) / days), shortfall, bufferFromPlan,
      steady: Boolean(raw.steady_mode || raw.basis?.steady_mode || raw.basis?.coaching_mode === 'steady')};
  }
  if (int(raw.starting_balance_cents) !== null && raw.next_payday) {
    const items = (raw.committed_items || []).map(item => ({
      kind: LOAN_TYPES.has(item.transaction_type) || (item.source === 'declared' && /loan|debt|mortgage/i.test(String(item.label))) ? 'loan' : 'bill',
      label: String(item.label || ''), amount: pos(item.amount_cents), date: item.date || null, told: TOLD_SOURCES.has(item.source),
    })).filter(item => item.amount);
    if (pos(raw.planned_saving_cents)) items.push({kind: 'goal', label: '', amount: pos(raw.planned_saving_cents), date: null, told: true, saving: true});
    const heldTotal = items.reduce((sum, item) => sum + item.amount, 0);
    const days = Math.max(1, int(raw.days_until_payday) ?? 1);
    const free = int(raw.free_cents) ?? 0;
    const extra = raw.safe_to_save_available === false ? 0 : Math.min(pos(raw.safe_to_save_cents), Math.max(free, 0));
    const spendable = Math.max(free, 0) - extra;
    return {shape: 'legacy', asOf: raw.reference_date || null, balance: int(raw.starting_balance_cents), nextPayday: raw.next_payday, days,
      paydayKnown: raw.payday_source !== 'fallback_30_days', items, heldTotal, reserve: pos(raw.reserve_floor_cents), buffer: 0,
      everyday: 0, spendable, extra, perDay: Math.floor(spendable / days), shortfall: Math.max(pos(raw.shortfall_cents), free < 0 ? -free : 0),
      bufferFromPlan: false, steady: Boolean(raw.steady_mode)};
  }
  return null;
}

/**
 * The plan's state: 'ok' (money for daily life), 'short' (bills before payday are more than the balance),
 * or 'tight' (bills are covered, but the safety cushion, surprise buffer or everyday basics are not).
 * billsGap: how much the bills miss by; left: what is left after the bills.
 */
export function planStatus(plan) {
  if (!plan) return null;
  const balance = Math.max(0, int(plan.balance) ?? 0);
  const billsGap = Math.max(0, plan.heldTotal - balance), left = Math.max(0, balance - plan.heldTotal);
  const state = billsGap > 0 ? 'short' : plan.shortfall > 0 ? 'tight' : 'ok';
  return {state, billsGap, left, balance};
}

/**
 * Bar segments (key, cents, share 0..1) for a normalized plan; shares sum to 1 when anything is shown.
 * The bar always splits the balance: when money runs short it shows what the balance covers instead of
 * drawing needs the account cannot hold.
 */
export function planSegments(plan) {
  if (!plan) return [];
  const status = planStatus(plan);
  let rows;
  if (status.state === 'short') rows = [['covered', status.balance], ['missing', status.billsGap]];
  else if (status.state === 'tight') rows = [['held', plan.heldTotal], ['afterBills', status.left]];
  else rows = [['held', plan.heldTotal], ['cushion', plan.reserve], ['surprise', plan.buffer], ['extra', plan.extra], ['everyday', plan.everyday], ['free', plan.spendable]];
  rows = rows.filter(([, cents]) => cents > 0);
  const total = rows.reduce((sum, [, cents]) => sum + cents, 0);
  return rows.map(([key, cents]) => ({key, cents, share: total ? cents / total : 0}));
}

/** Whole-euro parts of the daily-life money that add up visibly: everyday + free = total. */
export function dailyParts(plan) {
  const total = Math.round((plan.everyday + plan.spendable) / 100), everyday = Math.round(plan.everyday / 100);
  return {everyday: everyday * 100, free: (total - everyday) * 100, total: total * 100};
}

/** The active life event that put the profile into careful (steady) mode, or null. */
export function steadyEvent(profile) {
  const entries = (profile?.entries || []).filter(entry => entry.key === 'life_event' && entry.active !== false && entry.value && !entry.value.ended);
  const careful = entries.filter(entry => ['job_loss', 'income_drop', 'large_loss'].includes(entry.value.type));
  const list = careful.length ? careful : entries;
  if (!list.length) return null;
  return [...list].sort((a, b) => String(b.value.since || '').localeCompare(String(a.value.since || '')))[0].value.type;
}
const profileValue = (profile, key) => {
  const entry = (profile?.entries || []).find(item => item.key === key && item.active !== false);
  return entry ? entry.value : null;
};

/** Monthly set-aside, target and months for a surprise buffer from irregular_buffer data. */
export function bufferPlan(buffer) {
  if (!buffer || buffer.available === false) return null;
  const average = pos(buffer.suggested_monthly_set_aside_cents ?? buffer.monthly_average_cents);
  const monthly = Math.max(1000, Math.ceil(average / 1000) * 1000);
  const largest = pos(buffer.largest?.amount_cents);
  const target = Math.max(5000, Math.ceil(Math.max(largest, average * 3) / 5000) * 5000);
  return {monthly, target, months: Math.max(1, Math.ceil(target / monthly)), average, total: pos(buffer.total_cents), largest: buffer.largest || null, count: pos(buffer.count)};
}

/** Categories the customer asked the coach never to suggest cutting: server profile, plus the local preference. */
export function protectedCategories(profile, localPreference = null) {
  const list = profileValue(profile, 'protected_categories');
  const names = new Set((Array.isArray(list) ? list : []).map(name => String(name).toLowerCase()));
  if (localPreference && localPreference !== 'none') names.add(String(localPreference).toLowerCase());
  return names;
}

/** The biggest discretionary (everyday extra) category this month that is not protected, or null. */
export function topFlexibleCategory(rows = [], protectedNames = new Set()) {
  const totals = new Map();
  for (const row of rows || []) {
    if (row.role !== 'discretionary' || !(row.amount_cents < 0) || !row.category) continue;
    if (protectedNames.has(String(row.category).toLowerCase())) continue;
    totals.set(row.category, (totals.get(row.category) || 0) - row.amount_cents);
  }
  const [best] = [...totals].sort((a, b) => b[1] - a[1]);
  return best && best[1] >= 2000 ? {category: best[0], cents: best[1]} : null;
}

/** The month tiles: in / spent / left over, with change versus the previous month. */
export function monthTiles(overview, previous) {
  const values = data => {
    if (!data) return null;
    const income = int(data.salary_cents) !== null && int(data.other_income_cents) !== null ? data.salary_cents + data.other_income_cents : null;
    const spent = int(data.consumption_cents);
    return {in: income, out: spent, left: income !== null && spent !== null ? income - spent : null};
  };
  const now = values(overview), before = values(previous);
  if (!now) return [];
  return ['in', 'out', 'left'].filter(key => now[key] !== null).map(key => ({
    key, cents: now[key], delta: before && before[key] !== null ? now[key] - before[key] : null,
    good: key === 'out' ? -1 : 1,
  }));
}

/**
 * The one coach insight for Home: {kind, text, chips:[{label, attrs}]} (chips ≤ 2).
 * Priority: shortfall, careful mode, surprise buffer not yet planned, money beyond the usual need,
 * spending change versus last month, calm default.
 */
export function pickInsight({plan, profile, bufferInfo, hasBufferGoal, tiles = [], previousMonth = null, topCategory = null, categoryLabel = name => name, locale = 'en', fmt = formatters(locale)}) {
  const t = (key, values) => hm(locale, key, values);
  const ask = question => ({'data-direct-question': t(question)});
  const savingPct = profileValue(profile, 'saving_rate_target_pct');
  const told = Number.isFinite(Number(savingPct)) && Number(savingPct) > 0 ? ' ' + t('insight.savingTold', {pct: fmt.percent(savingPct)}) : '';
  if (plan?.steady || profile?.mode === 'steady')
    return {kind: 'steady', text: t('insight.steady'), chips: [{label: t('chip.ask'), attrs: ask('q.steady')}, plan && plan.shortfall > 0 ? {label: t('chip.due'), attrs: {'data-home-why': ''}} : {label: t('chip.situation'), attrs: {'data-view': 'profile'}}]};
  if (plan && plan.shortfall > 0)
    return {kind: 'shortfall', text: t('insight.shortfall'), chips: [{label: t('chip.ask'), attrs: ask('q.shortfall')}, {label: t('chip.due'), attrs: {'data-home-why': ''}}]};
  const idle = plan && plan.extra >= 10000 && plan.extra > Math.max(plan.spendable * 3, 500000);
  if (idle)
    return {kind: 'extra', text: t('insight.extra', {amount: fmt.whole(plan.extra)}) + told, chips: [{label: t('chip.goal'), attrs: {'data-home-goal': String(plan.extra)}, primary: true}, {label: t('chip.ask'), attrs: ask('q.save')}]};
  if (bufferInfo && bufferInfo.average > 0 && !hasBufferGoal)
    return {kind: 'buffer', text: t('insight.buffer', {amount: fmt.whole(bufferInfo.average)}) + told, chips: [{label: t('chip.bufferCard'), attrs: {'data-home-scroll': 'buffer'}}, {label: t('chip.where'), attrs: {'data-view': 'trends'}}]};
  if (plan && plan.extra >= 10000)
    return {kind: 'extra', text: t('insight.extra', {amount: fmt.whole(plan.extra)}) + told, chips: [{label: t('chip.goal'), attrs: {'data-home-goal': String(plan.extra)}, primary: true}, {label: t('chip.ask'), attrs: ask('q.save')}]};
  const out = tiles.find(tile => tile.key === 'out');
  if (out && out.delta && previousMonth && Math.abs(out.delta) >= 2000) {
    const key = out.delta < 0 ? 'insight.spentLess' : 'insight.spentMore';
    const text = t(key, {amount: fmt.whole(Math.abs(out.delta)), month: fmt.month(previousMonth)});
    if (out.delta > 0 && topCategory) {
      const category = categoryLabel(topCategory.category);
      return {kind: 'spentMore', text: text.replace(/\s*[^.!?]*\?$/, '') + ' ' + t('insight.topCategory', {category, amount: fmt.whole(topCategory.cents)}) + told,
        chips: [{label: t('chip.category', {category}), attrs: {'data-direct-question': t('q.category', {category})}}, {label: t('chip.where'), attrs: {'data-view': 'trends'}}]};
    }
    return {kind: out.delta < 0 ? 'spentLess' : 'spentMore', text: text + told, chips: [{label: t('chip.where'), attrs: {'data-view': 'trends'}}, {label: t('chip.ask'), attrs: ask('q.save')}]};
  }
  return {kind: 'calm', text: t('insight.calm', {amount: (fmt.floor || fmt.whole)(plan?.perDay ?? 0)}) + told, chips: [{label: t('chip.ask'), attrs: ask('q.safe')}, {label: t('chip.where'), attrs: {'data-view': 'trends'}}]};
}

const attrs = map => Object.entries(map || {}).map(([key, value]) => ` ${key}="${escape(value)}"`).join('');

/** The plan hero card HTML. options: {locale, fmt, label(item) -> text, profile, state:'loading'|'unavailable'|'ready'}. */
export function planCardHTML(plan, {locale = 'en', fmt = formatters(locale), label = item => item.label, profile = null, state = 'ready'} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const head = `<p class="hv4-eyebrow">${escape(t('eyebrow'))}</p>`;
  if (!plan) return `<section class="hv4-plan" aria-labelledby="home-v4-title" aria-busy="${state === 'loading'}">${head}<h2 id="home-v4-title" class="hv4-visually-hidden">${escape(t('title'))}</h2><p class="hv4-plan-empty">${escape(t(state === 'loading' ? 'loading' : 'unavailable'))}</p></section>`;
  const whole = fmt.whole, floor = fmt.floor || fmt.whole;
  const status = planStatus(plan), short = status.state === 'short', tight = status.state === 'tight';
  const segments = planSegments(plan), parts = dailyParts(plan);
  const payday = !plan.paydayKnown ? t('noPayday', {days: plan.days}) : plan.days === 1 ? t('paydayTomorrow', {date: fmt.shortDate(plan.nextPayday)}) : t('paydayIn', {days: plan.days, date: fmt.shortDate(plan.nextPayday)});
  const event = plan.steady ? steadyEvent(profile) : null;
  const steady = plan.steady ? `<p class="hv4-steady" role="note">${escape(t('steady', {event: t('event.' + (event && ['job_loss', 'income_drop', 'large_loss'].includes(event) ? event : 'other'))}))}</p>` : '';
  const savingPct = profileValue(profile, 'saving_rate_target_pct');
  const itemLabel = item => item.saving ? (Number(savingPct) > 0 ? t('kind.savingPct', {pct: fmt.percent(savingPct)}) : t('kind.saving'))
    : item.kind === 'tax' && !item.label ? t('kind.tax') : item.kind === 'loan' && !item.label ? t('kind.loan') : label(item);
  const segLabel = key => t(key === 'extra' && plan.steady ? 'seg.extraSteady' : key === 'covered' ? 'seg.covered' : key === 'missing' ? 'seg.missing' : key === 'held' && tight ? 'seg.bills' : 'seg.' + key);
  const segValue = s => (s.key === 'everyday' ? parts.everyday : s.key === 'free' ? parts.free : s.cents);

  // The cause, in plain words with whole euros: bills versus balance first, then what the plan cannot keep.
  let cause = '';
  if (short) {
    const bills = plan.items.length === 1 ? `${itemLabel(plan.items[0])} ${whole(plan.items[0].amount)}` : whole(plan.heldTotal);
    const first = t(plan.items.length === 1 ? 'short.bills' : 'short.billsMany', {bills, gap: whole(status.billsGap), balance: whole(status.balance)});
    const second = plan.reserve && plan.buffer ? t('short.cushionBuffer', {cushion: whole(plan.reserve), buffer: whole(plan.buffer)}) : plan.reserve ? t('short.cushion', {cushion: whole(plan.reserve)}) : '';
    cause = `<p class="hv4-cause" role="note">${escape([first, second].filter(Boolean).join(' '))}</p>`;
  } else if (tight) {
    const text = t('left.covered') + ' ' + t(plan.steady ? 'left.steady' : 'left.cushion', {left: whole(status.left), cushion: whole(plan.reserve)});
    cause = `<p class="hv4-cause" role="note">${escape(text)}</p>`;
  }

  let hero;
  if (short) hero = `<span class="hv4-hero-lead">${escape(t('short.lead'))}</span><span class="hv4-hero-amount">${escape(whole(status.billsGap))}</span><span class="hv4-hero-unit">${escape(t('short.unit'))}</span>`;
  else if (tight) hero = `<span class="hv4-hero-lead">${escape(t('left.lead'))}</span><span class="hv4-hero-amount">${escape(whole(status.left))}</span><span class="hv4-hero-unit">${escape(t('left.unit'))}</span>`;
  else hero = `<span class="hv4-hero-lead">${escape(t('canUse'))}</span><span class="hv4-hero-amount">${escape(floor(plan.perDay))}</span><span class="hv4-hero-unit">${escape(plan.paydayKnown ? t('perDay') : t('perDayFallback', {days: plan.days}))}</span><span class="hv4-hero-total">${escape(t('perDayTotal', {total: whole(parts.total)}))}</span>`;

  const bar = segments.length ? `<div class="hv4-bar" role="img" aria-label="${escape(segments.map(s => segLabel(s.key) + ' ' + whole(segValue(s))).join(', '))}">${segments.map(s => `<span class="hv4-seg hv4-seg-${s.key}" style="flex-grow:${Math.max(s.share, 0.015).toFixed(4)}"></span>`).join('')}</div>` : '';
  const legend = segments.length ? `<ul class="hv4-legend">${segments.map(s => `<li><i class="hv4-dot hv4-seg-${s.key}" aria-hidden="true"></i><span>${escape(segLabel(s.key))}</span><b>${escape(whole(segValue(s)))}</b></li>`).join('')}</ul>` : '';
  const sum = status.state === 'ok' && plan.everyday && plan.spendable ? `<p class="hv4-legend-sum">${escape(t('seg.sum', {everyday: whole(parts.everyday), free: whole(parts.free), total: whole(parts.total), perDay: floor(plan.perDay)}))}</p>` : '';

  const row = (text, cents, {sign = '−', date = null, told = false, strong = false, cls = '', sub = ''} = {}) => `<li class="${[strong ? 'hv4-why-total' : '', cls].filter(Boolean).join(' ')}"><span>${escape(text)}${date ? `<small>${escape(fmt.dayMonth(date))}</small>` : ''}${told ? `<small class="hv4-told">${escape(t('told'))}</small>` : ''}${sub ? `<small class="hv4-why-sub">${escape(sub)}</small>` : ''}</span><b>${sign ? sign + ' ' : ''}${escape(fmt.money(cents))}</b></li>`;
  const reserveLabel = t(plan.steady ? 'why.reserveSteady' : 'why.reserve'), bufferLabel = t(plan.bufferFromPlan ? 'why.bufferPlan' : 'why.buffer');
  const lines = [row(t('why.balance'), plan.balance, {sign: ''})];
  for (const item of plan.items) lines.push(row(itemLabel(item), item.amount, {date: item.date, told: item.told}));
  let after = '';
  if (short || tight) {
    lines.push(row(t(short ? 'why.short' : 'why.left'), short ? status.billsGap : status.left, {sign: short ? '−' : '=', strong: true}));
    const missing = [];
    if (plan.reserve) missing.push(row(reserveLabel, plan.reserve, {sign: ''}));
    if (plan.buffer) missing.push(row(bufferLabel, plan.buffer, {sign: ''}));
    if (plan.everyday) missing.push(row(t('why.everyday'), plan.everyday, {sign: ''}));
    if (missing.length) after = `<p class="hv4-why-sub-head">${escape(t(short ? 'why.notKept' : 'why.notFull'))}</p><ul class="hv4-why-list hv4-why-missing">${missing.join('')}</ul>`;
  } else {
    if (plan.reserve) lines.push(row(reserveLabel, plan.reserve));
    if (plan.buffer) lines.push(row(bufferLabel, plan.buffer));
    if (plan.extra) lines.push(row(t(plan.steady ? 'why.extraSteady' : 'why.extra'), plan.extra));
    const total = plan.everyday + plan.spendable;
    lines.push(row(t('why.daily'), total, {sign: '=', strong: true, sub: plan.everyday ? t('why.dailyParts', {everyday: fmt.money(plan.everyday), free: fmt.money(plan.spendable)}) : ''}));
    after = `<p class="hv4-why-perday">${escape(t('why.perDay', {amount: fmt.money(total), days: plan.days, perDay: floor(plan.perDay)}))}</p>`;
  }
  const why = `<details class="hv4-why" id="home-v4-why"><summary>${escape(t('why'))}</summary><ul class="hv4-why-list">${lines.join('')}</ul>${after}<p class="hv4-why-note">${escape(t('why.note'))}</p></details>`;
  const tone = short || tight ? ' hv4-plan-short' : plan.steady ? ' hv4-plan-steady' : '';
  return `<section class="hv4-plan${tone}" data-plan-state="${status.state}" aria-labelledby="home-v4-title">${head}<h2 id="home-v4-title" class="hv4-hero">${hero}</h2><p class="hv4-payday">${escape(payday)}</p>${steady}${cause}<div class="hv4-split"><p class="hv4-balance"><span>${escape(t(short ? 'seg.bills' : 'balance'))}</span><b>${escape(fmt.money(short ? plan.heldTotal : plan.balance))}</b></p>${bar}${legend}${sum}</div>${why}</section>`;
}

/** The insight card HTML. */
export function insightHTML(insight, {locale = 'en'} = {}) {
  if (!insight) return '';
  const chips = insight.chips.slice(0, 2).map(chip => `<button type="button" class="hv4-chip${chip.primary ? ' hv4-chip-primary' : ''}"${attrs(chip.attrs)}>${escape(chip.label)}</button>`).join('');
  return `<section class="hv4-card hv4-insight" data-insight="${escape(insight.kind)}" aria-label="${escape(hm(locale, 'insight.eyebrow'))}"><p class="hv4-insight-head"><span class="hv4-coach-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 15v-4h5V7h6m-4 0h4v4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>${escape(hm(locale, 'insight.eyebrow'))}</p><p class="hv4-insight-text">${escape(insight.text)}</p><div class="hv4-chips">${chips}</div></section>`;
}

/** This month card HTML. monthOptions is the <option> list for the month picker. */
export function monthHTML(tiles, {locale = 'en', fmt = formatters(locale), month = null, previousMonth = null, monthOptions = ''} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const picker = monthOptions ? `<label class="hv4-month-pick"><span class="hv4-visually-hidden">${escape(t('month.choose'))}</span><select id="home-v4-month-select">${monthOptions}</select></label>` : `<span class="hv4-month-label">${escape(month ? fmt.monthYear(month) : '')}</span>`;
  const body = tiles.length ? `<dl class="hv4-tiles">${tiles.map(tile => {
    const delta = tile.delta;
    const tone = delta === null || delta === 0 ? 'same' : (delta * tile.good > 0 ? 'good' : 'watch');
    const change = delta === null || !previousMonth ? '' : `<small class="hv4-delta hv4-delta-${tone}">${delta === 0 ? escape(t('month.same', {month: (fmt.monthShort || fmt.month)(previousMonth)})) : `<span aria-hidden="true">${delta > 0 ? '▲' : '▼'}</span> ${escape(t('month.vs', {amount: fmt.whole(Math.abs(delta)), month: (fmt.monthShort || fmt.month)(previousMonth)}))}`}</small>`;
    return `<div class="hv4-tile hv4-tile-${tile.key}"><dt>${escape(t('month.' + tile.key))}</dt><dd><b>${escape(tile.cents < 0 ? '\u2212' + fmt.whole(-tile.cents) : fmt.whole(tile.cents))}</b>${change}</dd></div>`;
  }).join('')}</dl>` : emptyStateHTML({kind: 'coin', compact: true, title: emptyText(locale, 'v5.em.home.month.title'), body: t('month.empty'), esc: escape, id: 'home-month'});
  return `<section class="hv4-card hv4-month" aria-labelledby="home-v4-month-title"><div class="hv4-card-head"><h2 id="home-v4-month-title">${escape(t('month.title'))}</h2>${picker}</div>${body}</section>`;
}

/**
 * Surprise buffer card HTML. goal: an existing goal with template 'buffer', or null.
 * heldNow: what this payday's plan holds back for surprise costs (cents). steady: no new saving is suggested.
 */
export function bufferHTML(info, goal, {locale = 'en', fmt = formatters(locale), readyBy = null, tight = false, steady = false, heldNow = 0, fromPlan = false} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const head = `<div class="hv4-card-head"><h2 id="home-v4-buffer-title">${escape(t('buffer.title'))}</h2>${goal ? `<button type="button" class="hv4-link" data-goal-edit="${escape(goal.id || goal.goal_id)}">${escape(t('buffer.change'))}</button>` : ''}</div>`;
  const open = `<section class="hv4-card hv4-buffer" id="home-v4-buffer-card" aria-labelledby="home-v4-buffer-title">`;
  if (goal) {
    const saved = pos(goal.current_saved_cents), target = pos(goal.target_cents), share = target ? Math.min(1, saved / target) : 0;
    const status = steady ? t('buffer.pausedGoal') : t('buffer.planned', {amount: fmt.whole(pos(goal.required_monthly_cents)), date: fmt.date(goal.target_date)});
    // Only claim what the payday plan really holds back for the saved plan (the server holds it back once it knows the plan).
    const monthly = pos(goal.required_monthly_cents), reflected = fromPlan || (monthly > 0 && heldNow >= Math.round(monthly * 0.95));
    const held = !steady && heldNow > 0 && reflected ? `<p class="hv4-buffer-held">${escape(t('buffer.heldNow', {amount: fmt.whole(heldNow)}))}</p>` : '';
    return `${open}${head}<p class="hv4-buffer-amount">${escape(t('buffer.progress', {saved: fmt.whole(saved), target: fmt.whole(target)}))}</p><div class="hv4-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(share * 100)}" aria-label="${escape(t('buffer.progress', {saved: fmt.whole(saved), target: fmt.whole(target)}))}"><span style="width:${(share * 100).toFixed(1)}%"></span></div><p class="hv4-muted">${escape(status)}</p>${held}</section>`;
  }
  if (!info) return '';
  if (steady) return `${open}${head}<p class="hv4-muted">${escape(t('buffer.help'))}</p><p class="hv4-later hv4-paused">${escape(t('buffer.paused'))}</p></section>`;
  const basis = info.total && info.largest ? t('buffer.basis', {total: fmt.whole(info.total), largest: fmt.whole(pos(info.largest.amount_cents))}) : t('buffer.none');
  const held = heldNow > 0 && !tight ? `<p class="hv4-basis">${escape(t('buffer.thisPayday', {amount: fmt.whole(heldNow)}))}</p>` : '';
  const pace = readyBy && !tight ? t('buffer.pace', {amount: fmt.whole(info.monthly), date: fmt.date(readyBy)}) : '';
  return `${open}${head}<p class="hv4-muted">${escape(t('buffer.help'))}</p><div class="hv4-buffer-suggest"><span>${escape(t('buffer.suggest'))}</span><b>${escape(fmt.whole(info.target))}</b>${pace ? `<small>${escape(pace)}</small>` : ''}</div><p class="hv4-basis">${escape(basis)}</p>${held}${tight ? `<p class="hv4-later">${escape(t('buffer.later'))}</p>` : `<button type="button" class="hv4-button" data-home-buffer>${escape(t('buffer.action', {amount: fmt.whole(info.monthly)}))}</button>`}</section>`;
}

/**
 * Goals and plans summary HTML: active plans first (mortgage, tax, surprise buffer), then goals, then wishes.
 * plans: the /api/plans list ({id, on, monthly_cents}).
 */
export function goalsHTML(goals = [], wishes = [], {locale = 'en', fmt = formatters(locale), plans = []} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const planRow = (name, monthly, attrsMap, key = 'plan.held') => `<li><button type="button" class="hv4-goal hv4-plan-row"${attrs(attrsMap)}><span class="hv4-goal-name">${escape(name)}<small class="hv4-on">${escape(t('plan.on'))}</small></span><span class="hv4-goal-meta">${escape(int(monthly) && monthly > 0 ? t(key, {amount: fmt.whole(monthly)}) : t('plan.on'))}</span></button></li>`;
  const rows = [];
  for (const plan of (Array.isArray(plans) ? plans : [])) if (plan?.on && ['mortgage', 'tax'].includes(plan.id)) rows.push(planRow(t('plan.' + plan.id), plan.monthly_cents, {'data-view': 'goals'}));
  const buffer = goals.find(goal => goal.template === 'buffer');
  if (buffer) rows.push(planRow(t('plan.buffer'), buffer.required_monthly_cents, {'data-home-scroll': 'buffer'}, 'plan.monthly'));
  const list = goals.filter(goal => goal.template !== 'buffer').slice(0, 3);
  rows.push(...list.map(goal => {
    const saved = pos(goal.current_saved_cents), target = pos(goal.target_cents), share = target ? Math.min(1, saved / target) : 0;
    return `<li><button type="button" class="hv4-goal" data-view="goals"><span class="hv4-goal-name">${escape(goal.name)}</span><span class="hv4-goal-meta">${escape(goal.target_date ? t('goals.line', {saved: fmt.whole(saved), target: fmt.whole(target), date: fmt.date(goal.target_date)}) : t('buffer.progress', {saved: fmt.whole(saved), target: fmt.whole(target)}))}${int(goal.required_monthly_cents) ? ' · ' + escape(t('goals.monthly', {amount: fmt.whole(goal.required_monthly_cents)})) : ''}</span><span class="hv4-mini" aria-hidden="true"><span style="width:${(share * 100).toFixed(1)}%"></span></span></button></li>`;
  }));
  for (const wish of wishes.slice(-2).reverse()) if (rows.length < 5) rows.push(`<li><button type="button" class="hv4-goal" data-view="goals"><span class="hv4-goal-name">${escape(wish.title)}</span><span class="hv4-goal-meta">${escape(t('goals.wish'))}</span></button></li>`);
  const body = rows.length ? `<ul class="hv4-goals">${rows.join('')}</ul>` : emptyStateHTML({kind: 'goal', compact: true, title: t('goals.empty'), action: {label: t('goals.start'), attrs: {'data-view': 'goals'}}, esc: escape, id: 'home-goals'});
  return `<section class="hv4-card hv4-goals-card" aria-labelledby="home-v4-goals-title"><div class="hv4-card-head"><h2 id="home-v4-goals-title">${escape(t('goals.title'))}</h2><button type="button" class="hv4-link" data-view="goals">${escape(t('goals.all'))} <span aria-hidden="true">›</span></button></div>${body}</section>`;
}

/** Personalise row: a clear entry when the profile is empty, otherwise what the coach knows. */
export function personalHTML(profile, {locale = 'en'} = {}) {
  const t = (key, values) => hm(locale, key, values);
  const count = (profile?.entries || []).filter(entry => entry.active !== false && entry.key !== 'year_review').length;
  if (!profile || profile.empty || !count)
    return `<section class="hv4-personal hv4-personal-empty" aria-labelledby="home-v4-personal-title"><div><h2 id="home-v4-personal-title">${escape(t('personal.title'))}</h2><p>${escape(t('personal.help'))}</p></div><div class="hv4-personal-actions"><button type="button" class="hv4-button" data-home-intro>${escape(t('personal.start'))}</button><button type="button" class="hv4-link" data-open-notebook>${escape(t('personal.prefs'))}</button></div></section>`;
  return `<section class="hv4-personal" aria-labelledby="home-v4-personal-title"><h2 id="home-v4-personal-title" class="hv4-personal-known">${escape(count === 1 ? t('personal.known1') : t('personal.known', {count}))}</h2><div class="hv4-personal-actions"><button type="button" class="hv4-link" data-view="profile">${escape(t('personal.review'))} <span aria-hidden="true">›</span></button><button type="button" class="hv4-link" data-open-notebook>${escape(t('personal.prefs'))}</button></div></section>`;
}

function addMonths(isoDate, months) {
  const [y, m] = isoDate.slice(0, 7).split('-').map(Number);
  const end = new Date(Date.UTC(y, m - 1 + months + 1, 0));
  return end.toISOString().slice(0, 10);
}

/**
 * Wire Home to the app. deps: {state, $, request, captureContext, isCurrent, navigate, changePeriod, perform,
 * locale(), money, monthLabel, shiftMonth, categoryName, localProfile(), v3(), refreshGoals(context), notify}.
 */
export function createHome(deps) {
  const {state, $} = deps;
  let data = {key: null, profile: null, buffer: null, plans: []};
  let planSettled = null;
  const locale = () => lang(deps.locale?.() || 'en');
  const fmt = () => {
    const base = formatters(locale());
    return deps.money ? {...base, money: deps.money} : base;
  };
  const keyOf = context => [context.customerId, context.month, context.generation].join('|');
  const bufferGoal = () => (state.goals || []).find(goal => goal.template === 'buffer') || null;
  // The server's own localized label wins; otherwise the category name in the customer's language.
  const label = item => item.labels?.[locale()] || ((item.kind === 'bill' || item.kind === 'loan') && deps.categoryName ? deps.categoryName(item.label) : item.label);
  const referenceDate = () => state.safeToSpend?.reference_date || state.safeToSpend?.as_of || state.overview?.latest_balance_date || null;

  function render({settled = false} = {}) {
    const root = $('home-v4');
    if (!root) return;
    if (settled) planSettled = state.generation + '|' + state.selectedMonth;
    const done = planSettled === state.generation + '|' + state.selectedMonth;
    const l = locale(), f = fmt();
    const plan = normalizePlan(state.safeToSpend);
    const fresh = data.key === keyOf({customerId: state.customerId, month: state.selectedMonth, generation: state.generation});
    const profile = fresh ? data.profile : null;
    const bufferInfo = fresh ? bufferPlan(data.buffer) : null;
    const previous = deps.previousOverview?.() || null;
    const previousMonth = previous && state.selectedMonth && deps.shiftMonth ? deps.shiftMonth(state.selectedMonth, -1) : null;
    const tiles = monthTiles(state.overview, previous);
    const local = (() => { try { return deps.localProfile?.() || {}; } catch { return {}; } })();
    const topCategory = topFlexibleCategory(state.categoryRows, protectedCategories(profile, local.protected_category));
    const insight = state.overview || plan ? pickInsight({plan, profile, bufferInfo, hasBufferGoal: Boolean(bufferGoal()), tiles, previousMonth, topCategory, categoryLabel: name => (deps.categoryName ? deps.categoryName(name) : name), locale: l, fmt: f}) : null;
    const reference = referenceDate();
    const wishes = local.wishes || [];
    $('home-v4-plan').innerHTML = planCardHTML(plan, {locale: l, fmt: f, label, profile, state: plan ? 'ready' : done ? 'unavailable' : 'loading'});
    $('home-v4-insight').innerHTML = insightHTML(insight, {locale: l});
    const months = [...String($('selected-month')?.innerHTML || '').matchAll(/value="(\d{4}-\d{2})"/g)].map(match => match[1]);
    const options = months.map(month => `<option value="${month}"${month === state.selectedMonth ? ' selected' : ''}>${escape(f.monthYear(month))}</option>`).join('');
    $('home-v4-month').innerHTML = state.overview ? monthHTML(tiles, {locale: l, fmt: f, month: state.selectedMonth, previousMonth, monthOptions: options}) : '';
    const select = $('home-v4-month-select');
    if (select && typeof select.addEventListener === 'function') {
      select.value = state.selectedMonth || '';
      select.addEventListener('change', () => { if (select.value && select.value !== state.selectedMonth) deps.changePeriod?.(select.value); });
    }
    const steady = Boolean(plan?.steady || profile?.mode === 'steady');
    $('home-v4-buffer').innerHTML = bufferHTML(bufferInfo, bufferGoal(), {locale: l, fmt: f, readyBy: bufferInfo && reference ? addMonths(reference, bufferInfo.months) : null,
      tight: Boolean(plan && plan.shortfall > 0), steady, heldNow: plan ? plan.buffer : 0, fromPlan: Boolean(plan?.bufferFromPlan)});
    $('home-v4-goals').innerHTML = state.overview ? goalsHTML(state.goals || [], wishes, {locale: l, fmt: f, plans: fresh ? data.plans : []}) : '';
    $('home-v4-personal').innerHTML = fresh ? personalHTML(profile, {locale: l}) : '';
  }

  async function onLoad(context = deps.captureContext()) {
    if (!context?.month) { render(); return; }
    const key = keyOf(context);
    // The previous month's overview is shared with the monthly recap cache (deps.previousOverview), not fetched twice.
    const [profile, spender, plans] = await Promise.allSettled([
      deps.request(context, 'get', '/api/profile', {month: context.month}),
      deps.request(context, 'get', '/api/spender-profile', {month: context.month}),
      deps.request(context, 'get', '/api/plans', {month: context.month}),
    ]);
    if (!deps.isCurrent(context) || context.month !== state.selectedMonth) return;
    data = {key,
      profile: profile.status === 'fulfilled' ? (profile.value?.profile || null) : null,
      buffer: spender.status === 'fulfilled' ? (spender.value?.buffer || null) : null,
      plans: plans.status === 'fulfilled' && Array.isArray(plans.value?.plans) ? plans.value.plans : []};
    render();
  }

  function openBufferDraft() {
    const info = bufferPlan(data.buffer) || {monthly: 5000, target: 50000, months: 10};
    const v3 = deps.v3?.();
    const reference = referenceDate() || new Date().toISOString().slice(0, 10);
    const l = locale(), f = fmt(), t = (key, values) => hm(l, key, values);
    const preview = values => {
      const target = pos(values.target_cents) - pos(values.current_saved_cents);
      if (!values.target_date || !(target > 0)) return '';
      const [fy, fm] = reference.split('-').map(Number), [ty, tm] = String(values.target_date).split('-').map(Number);
      const months = (ty - fy) * 12 + (tm - fm);
      return months >= 1 ? t('draft.preview', {amount: f.whole(Math.ceil(target / months)), months}) : '';
    };
    const spec = {id: 'home-buffer', kind: 'goal', title: t('draft.title'), intro: t('draft.intro', {amount: f.whole(info.monthly)}), saveLabel: t('draft.save'), fields: [
      {name: 'name', label: t('draft.name'), type: 'text', value: t('draft.defaultName'), required: true, max: 120},
      {name: 'target_cents', label: t('draft.target'), type: 'amount', value: info.target, required: true, min: 100},
      {name: 'target_date', label: t('draft.date'), type: 'date', value: addMonths(reference, info.months), required: true},
      {name: 'current_saved_cents', label: t('draft.saved'), type: 'amount', value: 0},
    ]};
    spec.preview = preview({target_cents: info.target, target_date: spec.fields[2].value, current_saved_cents: 0});
    const context = deps.captureContext();
    const save = async values => {
      await deps.request(context, 'post', '/api/goals', {name: values.name, target_cents: values.target_cents, target_date: values.target_date,
        current_saved_cents: values.current_saved_cents || 0, reserve_floor_cents: 50000, template: 'buffer', confirmed: true});
      await deps.refreshGoals?.(context);
      deps.notify?.(t('draft.saved.notice'));
    };
    if (v3?.openDraft) v3.openDraft(spec, {onSave: save, onChange: (values, card) => updateDraftPreview(card, preview(values))});
    else return deps.perform?.(null, () => save({name: t('draft.defaultName'), target_cents: info.target, target_date: spec.fields[2].value, current_saved_cents: 0}));
  }

  /** "Make it a goal": open the goal planner with a savings goal for the money that could be saved. */
  function openGoalPrefill(cents) {
    deps.navigate?.('goals');
    const planner = $('goal-planner');
    if (planner) planner.open = true;
    const set = (id, value) => { const el = $(id); if (el) el.value = value; };
    set('goal-template', 'custom');
    set('goal-name', hm(locale(), 'goal.savingsName'));
    if (Number.isFinite(cents) && cents > 0) set('goal-target', String(Math.floor(cents / 100)));
    const name = $('goal-name');
    const show = () => { name?.scrollIntoView?.({block: 'center'}); name?.focus?.({preventScroll: true}); };
    show();
    // The Goals page fills in its plans after navigation; show the form again once it has settled.
    if (typeof setTimeout === 'function') setTimeout(show, 450);
  }

  function handleClick(event) {
    const target = event?.target?.closest?.('[data-home-buffer],[data-home-why],[data-home-intro],[data-home-goal],[data-home-scroll]');
    if (!target || !target.dataset) return false;
    if (target.dataset.homeBuffer !== undefined) { openBufferDraft(); return true; }
    if (target.dataset.homeScroll !== undefined) {
      const card = $('home-v4-buffer-card');
      card?.scrollIntoView?.({block: 'center', behavior: 'smooth'});
      card?.querySelector?.('button')?.focus?.({preventScroll: true});
      return true;
    }
    if (target.dataset.homeGoal !== undefined) { openGoalPrefill(Number(target.dataset.homeGoal)); return true; }
    if (target.dataset.homeWhy !== undefined) {
      const why = $('home-v4-why');
      if (why) { why.open = true; why.scrollIntoView?.({block: 'center', behavior: 'smooth'}); }
      return true;
    }
    if (target.dataset.homeIntro !== undefined) {
      const v3 = deps.v3?.();
      if (v3?.startIntro) v3.startIntro(); else deps.navigate?.('profile');
      return true;
    }
    return false;
  }

  function reset() { data = {key: null, profile: null, buffer: null, plans: []}; planSettled = null; }

  // A Home error must never break the rest of the app.
  const guard = (fn, fallback) => (...args) => { try { const out = fn(...args); return out?.catch ? out.catch(error => { globalThis.console?.warn?.('[home]', error); }) : out; } catch (error) { globalThis.console?.warn?.('[home]', error); return fallback; } };
  return {render: guard(render), onLoad: guard(onLoad), handleClick: guard(handleClick, false), reset: guard(reset), openBufferDraft: guard(openBufferDraft)};
}
