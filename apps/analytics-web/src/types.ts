export interface AnalyticsQueryResponse {
  contract_version: 'v1';
  query_id: string;
  query: string;
  dataset: string;
  status: 'succeeded' | 'failed';
  sql: string;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  execution_time_ms: number;
  truncated: boolean;
  chart_spec: Record<string, unknown> | null;
  error: string;
  generated_at: string;
}

export interface HealthResponse {
  service: 'analytics-api';
  status: 'ready' | 'degraded';
  database_configured: boolean;
  llm_configured: boolean;
  contract_version: 'v1';
}
