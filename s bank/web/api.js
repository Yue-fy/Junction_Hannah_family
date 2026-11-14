export function agentHistory(conversation, { customerId, month, locale }) {
  // Only visible text from this conversation scope may leave the browser.
  const history = [];
  const clip = value => typeof value === 'string' ? Array.from(value.trim()).slice(0, 600).join('') : '';
  for (const turn of conversation) {
    if (!turn?.context || turn.context.customerId !== customerId || turn.context.month !== month || turn.context.locale !== locale) continue;
    const user = clip(turn.message);
    const paragraphs = turn.response?.source === 'agent' ? turn.response.answer : turn.paragraphs;
    const coach = clip(Array.isArray(paragraphs) ? paragraphs.filter(value => typeof value === 'string').join('\n\n') : turn.content);
    if (user) history.push({ role: 'user', text: user });
    if (coach) history.push({ role: 'coach', text: coach });
  }
  return history.slice(-8);
}

export function createAPI(customerId) {
  async function request(path, method, values = {}, timeoutMs = 10000) {
    const options = { method, headers: { 'Accept': 'application/json' } };
    let url = path;
    if (method === 'GET') {
      const query = new URLSearchParams({ customer_id: customerId });
      for (const [key, value] of Object.entries(values)) if (value !== null && value !== undefined) query.set(key, value);
      url += '?' + query;
    } else {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify({ ...values, customer_id: customerId });
    }
    const controller = new AbortController();
    options.signal = controller.signal;
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, options);
      const result = await response.json();
      if (!response.ok || result.ok === false || result.error) throw new Error(result.error?.message || (typeof result.error === 'string' ? result.error : `The request could not be completed (${response.status}).`));
      return result.data ?? result;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('This is taking longer than expected. Please try again.');
      if (error instanceof TypeError) throw new Error('We could not reach the demo server. Check the connection and try again.');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  return {
    get: (path, params, options = {}) => request(path, 'GET', params, options.timeout ?? 10000),
    post: (path, body, options = {}) => request(path, 'POST', body, options.timeout ?? 10000),
    agent: (message, { month, locale = 'en', conversation = [] }) => request('/api/agent', 'POST', {
      message, month, locale, history: agentHistory(conversation, { customerId, month, locale }),
    }, 40000),
  };
}
