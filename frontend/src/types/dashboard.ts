// 仪表盘总览
export interface DashboardOverview {
  period: {
    days: number;
    from: string;
    to: string;
  };
  sales: {
    total_amount: number;
    order_count: number;
    avg_order_value: number;
  };
  inventory: {
    total_in: number;
    total_out: number;
    net_change: number;
  };
  work_orders: {
    total: number;
    by_status: Record<string, number>;
  };
  alerts: {
    active: number;
    by_level: Record<string, number>;
  };
  agents: {
    total: number;
    by_autonomy_level: Record<string, number>;
  };
}

// 销售趋势
export interface SalesTrendPoint {
  date: string;
  amount: number;
  order_count: number;
  avg_value: number;
}

// 库存趋势
export interface InventoryTrendPoint {
  date: string;
  in: number;
  out: number;
  net: number;
}

// Agent 活动
export interface AgentActivity {
  total_work_orders: number;
  by_agent: Record<number, {
    name: string;
    count: number;
    by_status: Record<string, number>;
  }>;
  by_type: Record<string, number>;
}

// 效率对比（Agent vs 人工）
export interface EfficiencyComparison {
  period: { days: number };
  agent_created: {
    total: number;
    approved: number;
    rejected: number;
    approval_rate: number;
    rejection_rate: number;
    avg_processing_minutes: number;
  };
  manual_created: {
    total: number;
    approved: number;
    rejected: number;
    approval_rate: number;
    rejection_rate: number;
    avg_processing_minutes: number;
  };
}
