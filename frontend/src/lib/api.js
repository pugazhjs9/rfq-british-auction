export class ApiError extends Error {
  constructor(status, body) {
    super(body?.detail ?? `Request failed (${status})`);
    this.status = status;
    this.code = body?.code ?? null;
    this.fields = body?.errors ?? {};
  }
}

async function request(path, { method = 'GET', body, userId } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (userId != null) headers['X-User-Id'] = String(userId);
  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}

export const api = {
  time: () => request('/api/time'),
  users: () => request('/api/users'),
  // Reads are shaped for the user: suppliers only see competitors as aliases.
  auctions: (userId) => request('/api/rfqs', { userId }),
  auction: (id, userId) => request(`/api/rfqs/${id}`, { userId }),
  createRfq: (body, userId) => request('/api/rfqs', { method: 'POST', body, userId }),
  placeBid: (rfqId, body, userId) =>
    request(`/api/rfqs/${rfqId}/bids`, { method: 'POST', body, userId }),
};
