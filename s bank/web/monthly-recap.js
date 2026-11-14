// The agent selects observations; existing server tools and number checks own the facts.
export function monthlyRecapPrompt(month, locale) {
  const language = {en:'English',fi:'Finnish',sv:'Swedish'}[locale] || 'English';
  return `Write a monthly recap for ${month} for the Home card in ${language}. Call get_overview for this month first; compare_periods with the previous calendar month is optional. Copy preformatted euro values and precomputed percentages exactly; never do arithmetic yourself. Reply with exactly three short paragraphs separated by blank lines and nothing else: (1) the single most important thing about this month, at most twelve words; (2) one thing that went well, at most eighteen words; (3) one thing worth a look, at most eighteen words. No labels, headings, emoji or bold. Warm and matter-of-fact; never shame. Use the basket names Must-pays, Surprise must-pays and Little leaks if you mention baskets. Add one short follow-up question as a suggestion in the ui block.`;
}

function acceptedRecap(response) {
  if (response?.source !== 'agent' || !Array.isArray(response.answer) || !response.answer.length || response.answer.length > 3) return null;
  if (!Array.isArray(response.steps) || !response.steps.some(step => step?.tool === 'get_overview')) return null;
  if (response.answer.some(value => typeof value !== 'string' || !value.trim())) return null;
  const paragraphs = response.answer.map(value => value.replace(/\*\*/g, '').trim());
  if (paragraphs.some(value => !value)) return null;
  const text = paragraphs.join(' ');
  if (text.length > 600) return null;
  // The redesigned card shows a headline plus 'went well' and 'worth a look' lines when the model follows the format.
  const lines = paragraphs.length === 3 && paragraphs[0].length <= 110 && paragraphs.slice(1).every(value => value.length <= 160)
    ? {headline: paragraphs[0], good: paragraphs[1], watch: paragraphs[2]} : null;
  const question = Array.isArray(response.suggestions) ? response.suggestions.find(value => typeof value === 'string' && value.trim() && value.length <= 160) : null;
  return {text, lines, question: question?.trim() || null};
}

export function createMonthlyRecapCache() {
  const entries = new Map();
  return {
    get(key, request) {
      if (entries.has(key)) return entries.get(key);
      const entry = {pending:true, result:null, promise:null};
      entries.set(key, entry);
      if (entries.size > 12) entries.delete(entries.keys().next().value);
      entry.promise = Promise.resolve().then(request).then(response => {
        entry.result = acceptedRecap(response);
      }).catch(() => { entry.result = null; }).finally(() => { entry.pending = false; });
      return entry;
    },
  };
}

/** Stat tiles for income, spending and savings transfers with change versus the previous month. Pure. */
export function recapTiles(overview, previous) {
  const value = (data, key) => {
    if (!data) return null;
    if (key === 'income') return Number.isSafeInteger(data.salary_cents) && Number.isSafeInteger(data.other_income_cents) ? data.salary_cents + data.other_income_cents : null;
    const field = {spent:'consumption_cents', saved:'committed_saving_transfers_cents'}[key];
    return Number.isSafeInteger(data[field]) ? data[field] : null;
  };
  return ['income','spent','saved'].map(key => {
    const current = value(overview, key), before = value(previous, key);
    return {key, cents: current, delta_cents: current !== null && before !== null ? current - before : null};
  }).filter(tile => tile.cents !== null);
}
