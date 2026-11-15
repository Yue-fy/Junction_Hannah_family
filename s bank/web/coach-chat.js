// Render only the server's verified envelope. All text stays plain, apart from bold.
export function agentTurnHTML(turn, {esc, t, charts, flowName, latest = false}) {
  const response = turn.response;
  const plain = value => esc(typeof value === 'string' ? value : '');
  const prose = (response.answer || []).filter(value => typeof value === 'string')
    .flatMap(value => value.split(/\n\s*\n/)).filter(value => value.trim())
    .map(value => `<p>${plain(value).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')}</p>`).join('');
  const highlight = response.highlight;
  const stat = highlight ? `<section class="agent-highlight"><span>${plain(highlight.label)}</span><strong>${plain(highlight.value)}</strong><p>${plain(highlight.caption)}</p></section>` : '';
  const chart = response.chart;
  const series = (chart?.series || []).filter(row => Number.isSafeInteger(row.value_cents));
  let visual = '';
  if (series.length) {
    if (chart.kind === 'line') visual = charts.trendChart(series);
    else if (chart.kind === 'bar' || chart.kind === 'baskets') {
      visual = charts.barChart(series.map(row => ({...row, label: chart.kind === 'baskets' ? flowName(row.label) : row.label})));
    } else if (chart.kind === 'runway') visual = charts.runwayChart(series.map(row => ({date:row.label, balance_cents:row.value_cents, estimated:true})));
  }
  const steps = (response.steps || []).map(step => {
    const key = 'agent.step.' + step.tool, translated = t(key);
    return `<li>${plain(translated === key ? step.label : translated)}</li>`;
  }).join('');
  const evidence = (response.evidence || []).map((item,index) => `<button type="button" class="text-button" data-agent-evidence="${esc(turn.id)}" data-index="${index}">${plain(item.label)} <span aria-hidden="true">↗</span></button>`).join('');
  const work = steps || evidence ? `<details class="agent-work"><summary>${esc(t('agent.work'))}</summary>${steps ? `<ol>${steps}</ol>` : ''}${evidence}</details>` : '';
  const actions = (response.actions || []).map((action,index) => ['create_goal','save_scenario','open_view','update_goal','delete_goal','update_profile','open_year_review'].includes(action.kind) ? `<button type="button" class="secondary-button" data-agent-action="${esc(turn.id)}" data-index="${index}">${esc(t('agent.action.'+action.kind))} ↗</button>` : '').join('');
  const suggestions = latest ? (response.suggestions || []).filter(value => typeof value === 'string').slice(0,3).map((value,index) => `<button type="button" data-agent-suggestion="${esc(turn.id)}" data-index="${index}">${plain(value)}</button>`).join('') : '';
  return `<article class="coach-turn agent-turn"><p class="coach-turn-user">${plain(turn.message)}</p><div class="coach-turn-answer"><div class="coach-prose">${prose}</div>${stat}${visual ? `<figure class="agent-chart"><figcaption>${plain(chart.title)}</figcaption>${visual}</figure>` : ''}${work}${actions ? `<div class="agent-actions">${actions}</div>` : ''}</div>${suggestions ? `<div class="agent-suggestions" aria-label="${esc(t('agent.suggestions'))}">${suggestions}</div>` : ''}</article>`;
}
