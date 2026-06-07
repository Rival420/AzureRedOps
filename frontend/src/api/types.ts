export interface Assessment {
  id: number;
  name: string;
  client: string | null;
  description: string | null;
  scope_notes: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  token_count: number;
  job_count: number;
}

export interface VaultToken {
  id: number;
  assessment_id: number;
  name: string;
  tenant_id: string | null;
  username: string | null;
  scope: string | null;
  audience: string | null;
  expires: number | null;
  expires_human: string | null;
  is_expired: boolean | null;
  created_at: string;
}

export interface Job {
  id: number;
  assessment_id: number;
  activity: string;
  label: string | null;
  status: string;
  params: Record<string, unknown> | null;
  result: unknown;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobLog {
  id: number;
  ts: string;
  level: string;
  message: string;
}

export interface OperationField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  placeholder: string;
  help: string;
  default: unknown;
  options: string[];
}

export interface Operation {
  activity: string;
  name: string;
  description: string;
  long_running: boolean;
  fields: OperationField[];
}

export interface CatalogGroup {
  key: string;
  title: string;
  operations: Operation[];
}
