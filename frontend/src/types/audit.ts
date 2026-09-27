// 审计日志
export interface AuditLog {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  operator_id: string | null;
  operator_name: string;
  operator_type: 'user' | 'agent' | 'system';
  ip: string | null;
  result: 'success' | 'failure';
  detail: string | null;
  hash: string;
  prev_hash: string;
  created_at: string;
}

// 审计统计
export interface AuditStats {
  total: number;
  by_action: Record<string, number>;
  by_operator: Record<string, number>;
}

// 哈希链校验结果
export interface HashVerifyResult {
  valid: boolean;
  total_logs: number;
  broken_at?: number;
  broken_log?: AuditLog;
  expected_hash?: string;
  actual_hash?: string;
}
