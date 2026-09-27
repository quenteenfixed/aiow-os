// 告警级别
export type AlertLevel = 'P0' | 'P1' | 'P2' | 'P3';

// 告警类型
export type AlertType = 'inventory' | 'sales' | 'expiring' | 'system';

// 告警来源
export type AlertSource = 'system' | 'agent' | 'loop';

// 告警状态
export type AlertStatus = 'active' | 'acknowledged' | 'resolved';

// 告警
export interface Alert {
  id: number;
  level: AlertLevel;
  alert_type: AlertType;
  title: string;
  content: string;
  source: AlertSource;
  status: AlertStatus;
  metadata: Record<string, unknown> | null;
  related_id: string | null;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

// 告警汇总
export interface AlertsSummary {
  active: number;
  by_level: Record<AlertLevel, number>;
}
