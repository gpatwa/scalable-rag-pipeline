import type { AnalyticsQueryResponse, HealthResponse } from './types';

const API_BASE = import.meta.env.VITE_ANALYTICS_API_URL ?? '';
const API_KEY = import.meta.env.VITE_ANALYTICS_API_KEY ?? '';

const headers = (): HeadersInit => ({
  'Content-Type': 'application/json',
  ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
});

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error(`Health check failed (${response.status})`);
  return response.json() as Promise<HealthResponse>;
}

export async function runQuery(query: string): Promise<AnalyticsQueryResponse> {
  const response = await fetch(`${API_BASE}/api/v1/analytics/query`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({
      query,
      dataset: 'olist',
      tenant_id: 'local-demo',
      user_id: 'local-user',
    }),
  });
  if (!response.ok) throw new Error(`Analytics request failed (${response.status})`);
  return response.json() as Promise<AnalyticsQueryResponse>;
}
