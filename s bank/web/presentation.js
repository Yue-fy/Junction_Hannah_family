/** Pure presentation calculations. Source rows remain authoritative. */
export const CATEGORY_GROUPS = Object.freeze({
  everyday: Object.freeze(['Groceries','Transportation','Restaurants']),
  home: Object.freeze(['Housing','Utilities','Home & Tech','Health']),
  leisure: Object.freeze(['Lifestyle','Entertainment','Travel']),
});
const CONSUMPTION = new Set(['purchase','utilities_payment','housing_payment']);

export function spendingCategories(rows = [], group = 'all') {
  const totals = new Map();
  for (const row of rows) {
    if (!CONSUMPTION.has(row.transaction_type) || !Number.isSafeInteger(row.amount_cents) || row.amount_cents >= 0) continue;
    const category = row.category || 'Other';
    if (group !== 'all' && !CATEGORY_GROUPS[group]?.includes(category)) continue;
    if (!totals.has(category)) totals.set(category, {category,total_cents:0,count:0});
    const item = totals.get(category);
    item.total_cents -= row.amount_cents;
    item.count += 1;
  }
  return [...totals.values()].sort((a,b) => b.total_cents-a.total_cents || a.category.localeCompare(b.category));
}

export function forecastSummary(forecast) {
  const points = forecast?.projected || [];
  const valid = points.filter(row => Number.isSafeInteger(row.balance_cents));
  if (!valid.length) return null;
  const lowest = valid.reduce((a,b)=>a.balance_cents<=b.balance_cents?a:b);
  const end = valid.at(-1);
  return {end_cents:end.balance_cents,end_date:end.date,low_cents:lowest.balance_cents,low_date:lowest.date};
}

export function toolScope(response, fallbackMonth) {
  const result = response?.tool_result || {};
  const resolved = response?.query_scope || {};
  const start = resolved.start || result.start;
  const end = resolved.end || result.end;
  return {month:start?.slice(0,7)||fallbackMonth,...(start&&end?{start,end}:{}),...(resolved.filters||result.filters||{})};
}

export function milestoneFor(goals = []) {
  const goal = goals.find(item=>Number.isSafeInteger(item.target_cents)&&item.target_cents>0);
  if (!goal) return null;
  const percent = Math.min(100,Math.max(0,Math.floor((goal.current_saved_cents||0)*100/goal.target_cents)));
  const next = [25,50,75,100].find(value=>value>percent) || 100;
  return {name:goal.name,percent,next,remaining_cents:Math.max(0,Math.ceil(goal.target_cents*next/100)-(goal.current_saved_cents||0))};
}
