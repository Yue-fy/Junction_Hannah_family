// The agent selects observations; existing server tools and number checks own the facts.
export function monthlyRecapPrompt(month, locale) {
  const language = {en:'English',fi:'Finnish',sv:'Swedish'}[locale] || 'English';
  return `Write a monthly recap for ${month} for the Home card in ${language}. Call get_overview for this month first. It provides recorded income, consumption, savings transfers and top categories; copy its preformatted euro values. Choose only two useful observations, not an inventory of every figure. Write two short sentences, about forty to sixty words, as plain text without a heading. A previous-month comparison is optional; use compare_periods if helpful and copy its computed differences. Only call calculate for a needed new calculation, using euro values, not integer cent fields. If an optional tool fails, omit that calculation and summarize available facts. Do not do financial arithmetic yourself. Keep consumption separate from saving transfers. Salary and other income do not describe all incoming credits. Payment counts are not visits. Do not infer motives, household facts, investment returns or recommend cutting a spending category. Return one standalone, relevant follow-up question in suggestions; it must name the subject and period rather than refer to 'this' or 'it'. No chart, highlight or proposed actions are needed.`;
}

function acceptedRecap(response) {
  if (response?.source !== 'agent' || !Array.isArray(response.answer) || !response.answer.length || response.answer.length > 3) return null;
  if (!Array.isArray(response.steps) || !response.steps.some(step => step?.tool === 'get_overview')) return null;
  if (response.answer.some(value => typeof value !== 'string' || !value.trim())) return null;
  const paragraphs = response.answer.map(value => value.replace(/\*\*/g, '').trim());
  if (paragraphs.some(value => !value)) return null;
  const text = paragraphs.join(' ');
  if (text.length > 600) return null;
  const question = Array.isArray(response.suggestions) ? response.suggestions.find(value => typeof value === 'string' && value.trim() && value.length <= 160) : null;
  return {text, question: question?.trim() || null};
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
