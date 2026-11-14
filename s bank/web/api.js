export function createAPI(customerId) {
  async function request(path, method, values = {}) {
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
    const timeout = setTimeout(() => controller.abort(), 10000);
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
  return { get: (path, params) => request(path, 'GET', params), post: (path, body) => request(path, 'POST', body) };
}
