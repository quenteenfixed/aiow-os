// 工单类型
export type WorkOrderType =
  | 'price_adjust'
  | 'stock_in'
  | 'stock_out'
  | 'refund'
  | 'purchase_suggestion';

// 工单状态
export type WorkOrderStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'executing'
  | 'completed'
  | 'failed'
  | 'cancelled';

// 工单风险等级
export type RiskLevel = 'low' | 'medium' | 'high';

// 工单
export interface WorkOrder {
  id: number;
  order_type: WorkOrderType;
  title: string;
  description: string;
  reason: string | null;
  risk_level: RiskLevel;
  status: WorkOrderStatus;
  agent_id: number | null;
  agent_name: string | null;
  params: Record<string, unknown> | null;
  expected_result: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  approval_history?: ApprovalRecord[];
}

// 审批记录
export interface ApprovalRecord {
  id: number;
  action: 'submit' | 'approve' | 'reject' | 'cancel' | 'execute' | 'complete' | 'fail';
  operator_name: string;
  comment: string | null;
  modified_params: Record<string, unknown> | null;
  created_at: string;
}

// 创建工单
export interface WorkOrderCreate {
  order_type: WorkOrderType;
  title: string;
  description: string;
  reason?: string;
  params?: Record<string, unknown>;
  expected_result?: string;
  agent_id?: number;
}

// 审批请求
export interface ApproveRequest {
  comment?: string;
  modified_params?: Record<string, unknown>;
}

export interface RejectRequest {
  comment: string;
}
