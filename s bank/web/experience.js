/** Optional, user-controlled coaching context. Nothing here sends data to a server. */
export const EXPERIENCE_VERSION = 1;
export const PROFILE_PREFIX = 'scoach.experience.v1.';
export const TOUR_PREFIX = 'scoach.tour.v1.';
const FOCUS = ['buffer', 'travel', 'home', 'vehicle', 'flexibility'];
const STYLE = ['gentle', 'direct'];
const PROTECTED = ['Restaurants', 'Travel', 'Lifestyle', 'none'];
const NOTE_SOURCES = ['user', 'confirmed_conversation'];
const WISH_TEMPLATES = ['custom', 'buffer', 'trip', 'vehicle', 'home', 'purchase'];
const WISH_LIMIT = 20;
const memory = new WeakMap();
const noStorageMemory = new Map();
const clone = value => JSON.parse(JSON.stringify(value));
const cleanText = (value, max=500) => typeof value === 'string' ? value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').trim().slice(0, max) : '';
const defaults = () => ({focus:'flexibility',style:'gentle',protected_category:'none',milestones:false,consent:false,notes:[],wishes:[],onboarding_complete:false});
let sequence=0;
const noteId = () => 'note-' + (globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${++sequence}`);
const wishId = () => 'wish-' + (globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${++sequence}`);
const isoDate = value => typeof value==='string' && /^\d{4}-\d{2}-\d{2}T/.test(value) && Number.isFinite(Date.parse(value));

function safeNote(note, fallbackId=false) {
  if(typeof note==='string') note={text:note};
  if(!note || typeof note!=='object' || Array.isArray(note))return null;
  const text=cleanText(note.text);
  if(!text)return null;
  const id=typeof note.id==='string' && /^[a-zA-Z0-9_-]{1,90}$/.test(note.id) ? note.id : fallbackId ? noteId() : null;
  if(!id)return null;
  return {id,text,created_at:isoDate(note.created_at)?note.created_at:new Date().toISOString(),source:NOTE_SOURCES.includes(note.source)?note.source:'user'};
}
function wishFields(input, strict=false) {
  if(!input || typeof input!=='object' || Array.isArray(input)){
    if(strict)throw new Error('A valid wish is required');
    return null;
  }
  const title=cleanText(input.title,80);
  if(!title){
    if(strict)throw new Error('Enter a wish');
    return null;
  }
  const template=input.template===undefined?'custom':cleanText(input.template).toLowerCase();
  const contribution=input.contribution_cents===undefined?null:input.contribution_cents;
  const validContribution=contribution===null||Number.isSafeInteger(contribution)&&contribution>=0;
  if(strict&&!WISH_TEMPLATES.includes(template))throw new Error('Choose a valid wish template');
  if(strict&&!validContribution)throw new Error('Contribution must be nonnegative integer cents or empty');
  return {title,template:WISH_TEMPLATES.includes(template)?template:'custom',contribution_cents:validContribution?contribution:null};
}
function safeWish(input) {
  const fields=wishFields(input);
  if(!fields)return null;
  const id=typeof input.id==='string'?input.id.trim():'';
  if(!/^[a-zA-Z0-9_-]{1,90}$/.test(id))return null;
  const date=cleanText(input.created_at);
  return {id,...fields,created_at:isoDate(date)?new Date(date).toISOString():new Date().toISOString()};
}
function normalize(input) {
  const profile=defaults();
  if(!input || typeof input!=='object' || Array.isArray(input))return profile;
  if(FOCUS.includes(input.focus))profile.focus=input.focus;
  if(STYLE.includes(input.style))profile.style=input.style;
  if(PROTECTED.includes(input.protected_category))profile.protected_category=input.protected_category;
  profile.milestones=input.milestones===true;
  profile.consent=input.consent===true;
  profile.onboarding_complete=input.onboarding_complete===true;
  const seen=new Set();
  profile.notes=(Array.isArray(input.notes)?input.notes:[]).map(note=>safeNote(note)).filter(note=>{
    if(!note||seen.has(note.id))return false;
    seen.add(note.id);return true;
  }).slice(-50);
  const seenWishes=new Set();
  profile.wishes=(Array.isArray(input.wishes)?input.wishes:[]).map(wish=>safeWish(wish)).filter(wish=>{
    if(!wish||seenWishes.has(wish.id))return false;
    seenWishes.add(wish.id);return true;
  }).slice(-WISH_LIMIT);
  return profile;
}

/** Local profile with explicit consent. save() cannot grant consent. */
export function createExperienceStore(storage, customerId) {
  if(typeof customerId!=='string'||!/^\w[\w-]{0,63}$/.test(customerId))throw new Error('A valid persona is required');
  const usable=storage && (typeof storage==='object'||typeof storage==='function');
  const sessions=usable?(memory.get(storage)||new Map()):noStorageMemory;
  if(usable&&!memory.has(storage))memory.set(storage,sessions);
  const key=PROFILE_PREFIX+customerId, tourKey=TOUR_PREFIX+customerId;
  const read=key=>{try{return storage?.getItem(key)??null;}catch{return null;}};
  const remove=key=>{try{storage?.removeItem(key);return true;}catch{return false;}};
  const write=(key,value)=>{try{if(!storage?.setItem)return false;storage.setItem(key,value);return true;}catch{return false;}};
  let persistent=false, lastDeletionSuccessful=null;
  const clearSavedProfile=()=>{
    const removed=remove(key);
    lastDeletionSuccessful=removed||write(key,JSON.stringify({version:EXPERIENCE_VERSION,profile:{consent:false}}));
    return lastDeletionSuccessful;
  };
  if(!sessions.has(customerId)){
    let profile=defaults();
    try{
      const raw=read(key);
      if(raw&&raw.length<=40000){
        const envelope=JSON.parse(raw);
        if(envelope?.version===EXPERIENCE_VERSION&&envelope.profile?.consent===true)profile=normalize(envelope.profile);
        else remove(key);
      }else if(raw)remove(key);
    }catch{remove(key);}
    profile.onboarding_complete=profile.onboarding_complete||read(tourKey)==='1';
    sessions.set(customerId,profile);
  }
  const get=()=>sessions.get(customerId);
  const persist=()=>{
    if(get().consent)persistent=write(key,JSON.stringify({version:EXPERIENCE_VERSION,profile:get()}));
    else {remove(key);persistent=false;}
    return clone(get());
  };
  return {
    load(){return clone(get());},
    save(patch={}){
      const current=get();
      // Notes and wishes require explicit add/edit/delete methods.
      const fields=patch&&typeof patch==='object'?patch:{};
      const next=normalize({...current,...fields,notes:current.notes,wishes:current.wishes,consent:current.consent,onboarding_complete:current.onboarding_complete});
      sessions.set(customerId,next);
      return persist();
    },
    setConsent(allowed){
      if(allowed===true){lastDeletionSuccessful=null;get().consent=true;return persist();}
      // Revoking an earlier opt-in clears memory. Declining initially keeps this visit useful.
      if(get().consent){
        const onboarded=get().onboarding_complete;
        sessions.set(customerId,{...defaults(),onboarding_complete:onboarded});
      }
      clearSavedProfile();
      persistent=false;
      return clone(get());
    },
    forget(){
      sessions.set(customerId,defaults());
      clearSavedProfile();
      remove(tourKey);persistent=false;
      return clone(get());
    },
    addNote(input){
      const note=safeNote(input,true);
      if(!note)throw new Error('Enter a note');
      if(get().notes.length>=50)throw new Error('Notebook is full');
      note.id=noteId();
      get().notes.push(note);persist();
      return clone(note);
    },
    updateNote(id,text){
      const note=get().notes.find(note=>note.id===id);
      const cleaned=cleanText(text);
      if(!note||!cleaned)throw new Error('A valid note is required');
      note.text=cleaned;persist();return clone(note);
    },
    deleteNote(id){
      get().notes=get().notes.filter(note=>note.id!==id);return persist();
    },
    addWish(input){
      const fields=wishFields(input,true);
      if(get().wishes.length>=WISH_LIMIT)throw new Error('Wish list is full');
      const wish={id:wishId(),...fields,created_at:new Date().toISOString()};
      get().wishes.push(wish);persist();return clone(wish);
    },
    updateWish(id,patch){
      const wish=get().wishes.find(wish=>wish.id===id);
      if(!wish||!patch||typeof patch!=='object'||Array.isArray(patch))throw new Error('A valid wish is required');
      const fields=wishFields({...wish,...patch},true);
      Object.assign(wish,fields);persist();return clone(wish);
    },
    deleteWish(id){
      get().wishes=get().wishes.filter(wish=>wish.id!==id);return persist();
    },
    markOnboarded(){get().onboarding_complete=true;write(tourKey,'1');if(get().consent)persist();return clone(get());},
    isOnboarded(){return get().onboarding_complete===true;},
    // A successful storage write is reported separately from the user's consent choice.
    isPersisted(){return get().consent && read(key)===JSON.stringify({version:EXPERIENCE_VERSION,profile:get()});},
    isCleared(){return lastDeletionSuccessful===true;},
  };
}

/** Propose only explicit, bounded preferences. Confirmation and storage are separate UI actions. */
export function suggestedMemory(message, locale='en') {
  if(typeof message!=='string'||message.length>1000)return null;
  const value=message.trim().toLocaleLowerCase();
  if(!value||/\?|\b(?:not|never|don't|do not|doesn't|isn't|cannot|can't)\s+(?:want|prefer)|\b(?:maybe|might|perhaps|if|someone|friend|sister|brother)\b/.test(value))return null;
  const explicitGoal=/^(?:i want to save for|my savings goal is|haluan säästää|säästötavoitteeni on|jag vill spara till|mitt sparmål är)\s+/u.test(value);
  if(explicitGoal){
    const choices=[['buffer',/\b(?:emergency|buffer|puskur|hätävara|buffert)/u],['travel',/\b(?:trip|travel|holiday|vacation|matka|loma|resa|semester)/u],['home',/\b(?:home|house|apartment|asunto|koti|hem|bostad)/u],['vehicle',/\b(?:car|vehicle|auto|bil|fordon)/u]];
    const matches=choices.filter(([,pattern])=>pattern.test(value));
    if(matches.length===1){const focus=matches[0][0];return {field:'focus',value:focus,text:ux(locale,'memory.focus',{focus:ux(locale,'focus.'+focus)})};}
  }
  if(/^(?:i prefer|haluan|suosin|jag föredrar|jag vill ha)\s+/u.test(value)){
    // Mixed or negated styles need a fresh explicit choice, never a guessed preference.
    if(/\b(?:not|no|never|don't|do not|inte|ej|en|ei)\b/u.test(value))return null;
    const gentle=/\b(?:gentle|kind|calm|lempe|rauhalli|varsam|lugn)/u.test(value);
    const direct=/\b(?:direct|straightforward|suora|tydlig|rak)/u.test(value);
    if(gentle===direct)return null;
    const style=gentle?'gentle':'direct';
    return {field:'style',value:style,text:ux(locale,'memory.style',{style:ux(locale,'style.'+style)})};
  }
  if(/^(?:do not cut|don't cut|i want to protect|i want to keep|en halua vähentää|haluan säilyttää|jag vill behålla|minska inte)\s+/u.test(value)){
    const choices=[['Restaurants',/\b(?:dining|restaurants?|eating out|ravintola|ulkona syö|restaurang)/u],['Travel',/\b(?:travel|holidays?|matka|loma|resor|semester)/u],['Lifestyle',/\b(?:shopping|clothes|ostok|vaat|shopping|kläder)/u]];
    const matches=choices.filter(([,pattern])=>pattern.test(value));
    if(matches.length===1){const category=matches[0][0];return {field:'protected_category',value:category,text:ux(locale,'memory.protect',{category:ux(locale,'category.'+category)})};}
  }
  return null;
}

/** A transaction journal describes source events, never a guessed biography. */
export function buildJournal(overview, rows=[], locale='en') {
  if(!overview||!Array.isArray(rows))return [];
  const start=overview.start||overview.month+'-01',end=overview.end||overview.observed_end;
  const eligible=rows.filter(row=>{
    if(!row||typeof row.date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(row.date)||!Number.isSafeInteger(row.amount_cents))return false;
    if(start&&row.date<start||end&&row.date>end)return false;
    if(overview.customer_id&&row.customer_id&&row.customer_id!==overview.customer_id)return false;
    if(overview.account_id&&row.account_id&&row.account_id!==overview.account_id)return false;
    return true;
  });
  const largest=eligible.filter(row=>row.amount_cents<0&&row.transaction_type==='purchase').sort((a,b)=>a.amount_cents-b.amount_cents)[0];
  return eligible.filter(row=>{
    return row.amount_cents>0&&['salary','other_income'].includes(row.transaction_type)||row.amount_cents<0&&row.transaction_type==='housing_payment'||row===largest;
  }).map(row=>{
    const kind=row.amount_cents>0?'income':row.transaction_type==='housing_payment'?'housing':'purchase';
    return {id:row.transaction_ref||`${row.date}-${kind}`,date:row.date,kind,title:ux(locale,'journal.'+kind),category:row.category||'',amount_cents:row.amount_cents,transaction_ref:row.transaction_ref||null,observed:true};
  }).sort((a,b)=>b.date.localeCompare(a.date)||a.kind.localeCompare(b.kind)).slice(0,8);
}

const COPY = {
  'coach.newQuestion':['Start a new question','Aloita uusi kysymys','Börja med en ny fråga'],
  'home.greeting':['Hi, {name}.','Hei, {name}.','Hej, {name}.'],
  'home.promise':['More room for your life.','Enemmän tilaa elämällesi.','Mer utrymme för ditt liv.'],
  'home.coachTitle':['A little clarity. A next step.','Selkeyttä ja seuraava askel.','Lite klarhet. Ett nästa steg.'],
  'home.coachHelp':['Ask about your spending, explore a change, or make a plan that feels like you.','Kysy menoistasi, kokeile muutosta tai tee sinulle sopiva suunnitelma.','Fråga om dina utgifter, prova en förändring eller gör en plan som passar dig.'],
  'home.coachAction':['Let’s talk money','Puhutaan rahasta','Vi pratar pengar'],
  'personal.title':['Make it yours','Tee tästä omasi','Gör det till ditt'],
  'personal.intro':['A few choices help your coach focus on what matters to you. You can change them anytime.','Muutama valinta auttaa valmentajaa keskittymään sinulle tärkeisiin asioihin. Voit muuttaa niitä milloin vain.','Några val hjälper din coach att fokusera på det som betyder något för dig. Du kan ändra dem när som helst.'],
  'personal.setup':['Personalize my coach','Mukauta valmentajaani','Anpassa min coach'],
  'personal.edit':['Edit preferences','Muokkaa toiveita','Ändra önskemål'],
  'personal.focus':['What would you like more room for?','Mille haluaisit enemmän tilaa?','Vad vill du ge mer utrymme?'],
  'personal.style':['How should your coach sound?','Millaista valmennusta toivot?','Hur ska din coach låta?'],
  'personal.protect':['Anything you want to keep enjoying?','Mistä haluat jatkossakin nauttia?','Något du vill fortsätta njuta av?'],
  'personal.protectHelp':['Your coach will offer alternatives rather than automatically suggesting cuts here.','Valmentajasi ehdottaa vaihtoehtoja sen sijaan, että vähentäisi näitä menoja automaattisesti.','Din coach föreslår alternativ i stället för att automatiskt föreslå nedskärningar här.'],
  'personal.milestones':['Show gentle goal milestones','Näytä lempeät tavoite-etapit','Visa varsamma delmål'],
  'personal.milestonesHelp':['Optional encouragement. No streaks, penalties, or pressure to spend.','Vapaaehtoista kannustusta ilman suoritusputkia, rangaistuksia tai kulutuspainetta.','Frivillig uppmuntran utan sviter, straff eller press att spendera.'],
  'personal.consent':['Remember my preferences on this browser','Muista toiveeni tässä selaimessa','Kom ihåg mina önskemål i den här webbläsaren'],
  'personal.consentHelp':['Only choices and notes you confirm are saved. Your conversation is not recorded in the notebook. This demo browser may be shared.','Vain vahvistamasi valinnat ja muistiinpanot tallennetaan. Keskustelua ei tallenneta muistikirjaan. Demoselain voi olla yhteiskäytössä.','Bara val och anteckningar du bekräftar sparas. Samtalet sparas inte i anteckningsboken. Demowebbläsaren kan vara delad.'],
  'personal.session':['Using your choices for this visit only.','Valintasi ovat käytössä vain tämän vierailun ajan.','Dina val används bara under detta besök.'],
  'personal.stored':['Saved on this browser for this demo profile.','Tallennettu tähän selaimeen tälle demoprofiilille.','Sparat i den här webbläsaren för denna demoprofil.'],
  'personal.storageUnavailable':['Your browser could not save these choices. They still work for this visit.','Selain ei voinut tallentaa valintoja. Ne toimivat silti tämän vierailun ajan.','Webbläsaren kunde inte spara valen. De fungerar ändå under detta besök.'],
  'personal.save':['Use these preferences','Käytä näitä toiveita','Använd dessa önskemål'],
  'personal.cancel':['Cancel','Peruuta','Avbryt'],
  'personal.close':['Close','Sulje','Stäng'],
  'personal.forget':['Forget my preferences and notes','Poista toiveeni ja muistiinpanoni','Glöm mina önskemål och anteckningar'],
  'personal.clearFailed':['Cleared for this visit. Your browser could not remove saved data. Clear this site’s data in your browser settings before sharing this device.','Poistettu tämän vierailun ajaksi. Selain ei voinut poistaa tallennettuja tietoja. Tyhjennä sivuston tiedot selaimen asetuksista ennen laitteen jakamista.','Rensat för detta besök. Webbläsaren kunde inte ta bort sparad data. Rensa webbplatsens data i webbläsarinställningarna innan du delar enheten.'],
  'personal.forgotten':['Preferences and notes cleared from this browser.','Toiveet ja muistiinpanot poistettu tästä selaimesta.','Önskemål och anteckningar har rensats från webbläsaren.'],
  'focus.buffer':['An emergency cushion','Taloudellinen puskuri','En ekonomisk buffert'],
  'focus.travel':['A trip to look forward to','Matka, jota odottaa','En resa att se fram emot'],
  'focus.home':['A place of my own','Oma koti','Ett eget hem'],
  'focus.vehicle':['Getting around','Liikkuminen','Att ta sig fram'],
  'focus.flexibility':['More everyday freedom','Enemmän vapautta arkeen','Mer frihet i vardagen'],
  'style.gentle':['Gentle and encouraging','Lempeä ja kannustava','Varsam och uppmuntrande'],
  'style.direct':['Clear and direct','Selkeä ja suora','Tydlig och rak'],
  'protect.none':['No preference for now','Ei mitään juuri nyt','Inget just nu'],
  'tour.title':['Your money. Your way.','Rahasi. Tavallasi.','Dina pengar. På ditt sätt.'],
  'tour.intro':['Start with a clear picture, then choose one small next step.','Aloita selkeästä kokonaiskuvasta ja valitse sitten yksi pieni askel.','Börja med en tydlig bild och välj sedan ett litet nästa steg.'],
  'tour.spendingTitle':['Tap to see where it went','Napauta ja näe, mihin rahasi menivät','Tryck och se vart pengarna gick'],
  'tour.spending':['Pick a slice or category to explore its transactions. Income and savings stay separate.','Valitse lohko tai luokka ja tutustu tapahtumiin. Tulot ja säästöt näytetään erikseen.','Välj en del eller kategori för att utforska transaktionerna. Inkomster och sparande visas separat.'],
  'tour.coachTitle':['Ask. Understand. Try a change.','Kysy. Ymmärrä. Kokeile muutosta.','Fråga. Förstå. Prova en förändring.'],
  'tour.coach':['Your coach helps with clear questions and asks you to clarify when something is missing.','Valmentajasi auttaa selkeissä kysymyksissä ja kysyy tarkennuksia, kun tietoja puuttuu.','Din coach hjälper med tydliga frågor och ber om förtydliganden när information saknas.'],
  'tour.preferencesTitle':['You choose what matters','Sinä päätät, mikä on tärkeää','Du väljer vad som är viktigt'],
  'tour.preferences':['Share an optional goal or preference. Nothing goes into your notebook without your confirmation.','Kerro halutessasi tavoitteesta tai toiveesta. Mitään ei lisätä muistikirjaan ilman vahvistustasi.','Dela ett frivilligt mål eller önskemål. Inget läggs i anteckningsboken utan din bekräftelse.'],
  'tour.skip':['Explore on my own','Tutustun itse','Jag utforskar själv'],
  'tour.next':['Next','Seuraava','Nästa'],
  'tour.back':['Back','Takaisin','Tillbaka'],
  'tour.done':['Let’s get started','Aloitetaan','Nu börjar vi'],
  'tour.replay':['Show me around','Esittele palvelu','Visa mig runt'],
  'tour.step':['{step} of {total}','{step}/{total}','{step} av {total}'],
  'notebook.title':['My coaching notebook','Valmennusmuistikirjani','Min coachningsbok'],
  'notebook.intro':['Your goals and protected spending guide suggestions. Other notes are personal reflections you can revisit.','Tavoitteesi ja säilytettävät menosi ohjaavat ehdotuksia. Muut muistiinpanot ovat omia pohdintojasi, joihin voit palata.','Dina mål och utgifter du vill behålla styr förslagen. Andra anteckningar är personliga reflektioner som du kan återvända till.'],
  'notebook.empty':['No notes yet. Add something you would like your coach to keep in mind.','Ei vielä muistiinpanoja. Lisää asia, jonka haluat valmentajasi huomioivan.','Inga anteckningar ännu. Lägg till något du vill att din coach tar hänsyn till.'],
  'notebook.add':['Add a note','Lisää muistiinpano','Lägg till en anteckning'],
  'notebook.placeholder':['For example: Sunday dinners with friends matter to me.','Esimerkiksi: Sunnuntaipäivälliset ystävien kanssa ovat minulle tärkeitä.','Till exempel: Söndagsmiddagar med vänner är viktiga för mig.'],
  'notebook.save':['Save note','Tallenna muistiinpano','Spara anteckning'],
  'notebook.edit':['Edit','Muokkaa','Ändra'],
  'notebook.delete':['Delete','Poista','Ta bort'],
  'notebook.user':['Written by you','Sinun kirjoittamasi','Skrivet av dig'],
  'notebook.confirmed':['Confirmed by you','Sinun vahvistamasi','Bekräftat av dig'],
  'notebook.remember':['Would you like your coach to remember this?','Haluatko valmentajasi muistavan tämän?','Vill du att din coach kommer ihåg detta?'],
  'notebook.confirm':['Yes, add this preference','Kyllä, lisää tämä toive','Ja, lägg till detta önskemål'],
  'notebook.dismiss':['Not now','Ei nyt','Inte nu'],
  'notebook.limit':['Keep notes under 500 characters.','Pidä muistiinpanot alle 500 merkissä.','Håll anteckningarna under 500 tecken.'],
  'memory.focus':['I want to make room for: {focus}.','Haluan enemmän tilaa tälle: {focus}.','Jag vill ge mer utrymme åt: {focus}.'],
  'memory.style':['I prefer coaching that is {style}.','Toivottu valmennustyyli: {style}.','Önskad coachningsstil: {style}.'],
  'memory.protect':['I want to protect spending on {category}.','En halua tinkiä näistä menoista: {category}.','Jag vill inte dra ner på: {category}.'],
  'journal.title':['Your money journal','Rahapäiväkirjasi','Din pengadagbok'],
  'journal.intro':['A few moments from your account, plus the meaning you choose to add.','Muutama tapahtuma tililtäsi ja merkitykset, jotka itse haluat lisätä.','Några händelser från ditt konto och den betydelse du själv vill lägga till.'],
  'journal.empty':['No journal moments in this period. Try another month.','Tältä ajalta ei ole päiväkirjatapahtumia. Kokeile toista kuukautta.','Inga dagbokshändelser under perioden. Prova en annan månad.'],
  'journal.income':['Income arrived','Tulo saapui','Inkomst kom in'],
  'journal.housing':['A housing payment','Asumismaksu','En boendebetalning'],
  'journal.purchase':['Your largest recorded purchase','Suurin kirjattu ostoksesi','Ditt största registrerade köp'],
  'journal.observed':['From your transactions','Tilitapahtumistasi','Från dina transaktioner'],
  'journal.view':['See this transaction','Näytä tapahtuma','Visa transaktionen'],
  'journal.reflection':['What did this month mean to you?','Mitä tämä kuukausi merkitsi sinulle?','Vad betydde den här månaden för dig?'],
  'journal.noBiography':['Transactions show payments. Only you can add the story behind them.','Tapahtumat näyttävät maksut. Vain sinä voit kertoa tarinan niiden takana.','Transaktionerna visar betalningar. Bara du kan berätta historien bakom dem.'],
  'milestone.title':['A little closer','Hieman lähempänä','Lite närmare'],
  'milestone.start':['Every plan starts with a first step.','Jokainen suunnitelma alkaa ensimmäisestä askeleesta.','Varje plan börjar med ett första steg.'],
  'milestone.quarter':['A quarter of the way to your goal.','Neljännes tavoitteestasi on koossa.','En fjärdedel av vägen till ditt mål.'],
  'milestone.half':['Halfway to something that matters to you.','Puolivälissä kohti sinulle tärkeää asiaa.','Halvvägs till något som är viktigt för dig.'],
  'milestone.near':['Your goal is getting closer. Keep your own pace.','Tavoitteesi lähestyy. Jatka omaan tahtiisi.','Ditt mål närmar sig. Fortsätt i din egen takt.'],
  'milestone.complete':['Your recorded savings have reached this target.','Kirjatut säästösi ovat saavuttaneet tavoitteen.','Ditt registrerade sparande har nått målet.'],
  'milestone.basis':['Based on the saved amount you entered. Planning does not move money.','Perustuu ilmoittamaasi säästösummaan. Suunnittelu ei siirrä rahaa.','Baserat på sparbeloppet du angav. Planering flyttar inte pengar.'],
  'spending.title':['Spending, made clear','Menot selkeästi','Utgifterna i klartext'],
  'spending.total':['Spent this month','Tämän kuukauden menot','Utgifter den här månaden'],
  'spending.all':['All spending','Kaikki menot','Alla utgifter'],
  'spending.everyday':['Everyday life','Arki','Vardagsliv'],
  'spending.home':['Home & essentials','Koti ja välttämättömät menot','Hem och nödvändigheter'],
  'spending.leisure':['Life & leisure','Elämä ja vapaa-aika','Liv och fritid'],
  'spending.tap':['Choose a slice or category','Valitse lohko tai luokka','Välj en del eller kategori'],
  'spending.rows':['View {count} transactions','Näytä {count} tapahtumaa','Visa {count} transaktioner'],
  'spending.share':['{percent}% of spending','{percent} % menoista','{percent} % av utgifterna'],
  'spending.excludes':['Income and savings transfers are shown separately.','Tulot ja säästösiirrot näytetään erikseen.','Inkomster och sparöverföringar visas separat.'],
  'spending.baskets':['Another way to understand your spending','Toinen tapa ymmärtää menojasi','Ett annat sätt att förstå dina utgifter'],
  'forecast.title':['30-day balance forecast','Saldon 30 päivän ennuste','Saldoprognos för 30 dagar'],
  'forecast.help':['See how your balance could change if recent income and spending patterns continue.','Katso, miten saldosi voisi muuttua, jos viimeaikaiset tulo- ja menotavat jatkuvat.','Se hur saldot kan förändras om de senaste inkomst- och utgiftsmönstren fortsätter.'],
  'forecast.summary':['Estimated balance in 30 days: {amount}','Arvioitu saldo 30 päivän kuluttua: {amount}','Beräknat saldo om 30 dagar: {amount}'],
  'forecast.lowest':['Lowest estimated balance: {amount}','Alin arvioitu saldo: {amount}','Lägsta beräknade saldo: {amount}'],
  'category.Housing':['Housing','Asuminen','Boende'],
  'category.Utilities':['Bills','Laskut','Räkningar'],
  'category.Groceries':['Groceries','Ruokaostokset','Matinköp'],
  'category.Transportation':['Transport','Liikenne','Transport'],
  'category.Restaurants':['Eating out','Ravintolat','Restaurang'],
  'category.Health':['Health','Terveys','Hälsa'],
  'category.Home & Tech':['Home & tech','Koti ja tekniikka','Hem och teknik'],
  'category.Lifestyle':['Shopping','Ostokset','Shopping'],
  'category.Entertainment':['Entertainment','Viihde','Nöjen'],
  'category.Travel':['Travel','Matkailu','Resor'],
};
Object.assign(COPY, {
  'nav.today':['Today','Tänään','Idag'],
  'nav.spending':['Spending','Menot','Utgifter'],
  'nav.journal':['Journal','Päiväkirja','Dagbok'],
  'home.title':COPY['home.promise'],
  'home.subtitle':['Know where you stand. Choose what comes next.','Tiedä, missä mennään. Valitse seuraava askel.','Se var du står. Välj nästa steg.'],
  'period.help':['Explore a month from your account history.','Tutustu tilihistoriasi kuukauteen.','Utforska en månad i din kontohistorik.'],
  'balance.title':['Available balance','Käytettävissä oleva saldo','Tillgängligt saldo'],
  'balance.caption':['Your latest recorded account balance','Tilisi viimeisin kirjattu saldo','Ditt senast registrerade kontosaldo'],
  'balance.ask':['Ask my coach','Kysy valmentajalta','Fråga min coach'],
  'balance.details':['Account and data details','Tilin ja tietojen lisätiedot','Konto och datauppgifter'],
  'home.coach.eyebrow':['Your money coach','Oma rahavalmentajasi','Din pengacoach'],
  'home.coach.title':COPY['home.coachTitle'],
  'home.coach.help':COPY['home.coachHelp'],
  'home.coach.open':COPY['home.coachAction'],
  'spending.eyebrow':['The bigger picture','Kokonaiskuva','Den större bilden'],
  'spending.groups':['Spending category groups','Menoluokkien ryhmät','Grupper av utgiftskategorier'],
  'spending.basketsHelp':['Learn which costs repeat, which arrive unexpectedly, and which you choose day to day.','Tutustu toistuviin, yllättäviin ja päivittäin valittaviin menoihin.','Lär känna kostnader som återkommer, kommer oväntat och väljs dag för dag.'],
  'home.priority':['One thing worth a look','Yksi huomionarvoinen asia','En sak värd att se närmare på'],
  'forecast.eyebrow':['A look ahead','Katse eteenpäin','En blick framåt'],
  'forecast.understand':['Understand this estimate','Ymmärrä tämä arvio','Förstå denna uppskattning'],
  'forecast.explanation':['Based on recent patterns, with room for real life to change.','Perustuu viimeaikaisiin tapoihin. Elämä voi muuttua.','Baserat på de senaste mönstren. Verkligheten kan förändras.'],
  'forecast.adjust':['Adjust the assumptions','Muokkaa oletuksia','Ändra antagandena'],
  'safe.title':['Room to spend this week','Tämän viikon käyttövara','Utrymme att spendera denna vecka'],
  'personal.eyebrow':['Built around you','Sinun ehdoillasi','På dina villkor'],
  'personal.help':COPY['personal.intro'],
  'personal.action':COPY['personal.setup'],
  'journal.eyebrow':['Your money, your story','Rahasi, sinun tarinasi','Dina pengar, din berättelse'],
  'journal.help':COPY['journal.intro'],
  'journal.moments':['Moments this month','Tämän kuukauden tapahtumat','Händelser denna månad'],
  'journal.recorded':['Recorded activity','Kirjatut tapahtumat','Registrerade händelser'],
  'notebook.eyebrow':['The things that matter','Sinulle tärkeät asiat','Det som är viktigt för dig'],
  'notebook.help':COPY['notebook.intro'],
});
export const EXPERIENCE_MESSAGES=Object.freeze(Object.fromEntries(['en','fi','sv'].map((locale,index)=>[locale,Object.freeze(Object.fromEntries(Object.entries(COPY).map(([key,values])=>[key,values[index]])))])));
export const UX_MESSAGES=EXPERIENCE_MESSAGES;
export function ux(locale,key,values={}) {
  const normalized=String(locale||'en').toLowerCase().slice(0,2);
  const text=EXPERIENCE_MESSAGES[normalized]?.[key]||EXPERIENCE_MESSAGES.en[key]||key;
  return text.replace(/\{(\w+)\}/g,(_,name)=>values[name]===undefined?'{'+name+'}':String(values[name]));
}
