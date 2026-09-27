// Agent 状态
export type AgentStatus =
  | 'initializing'
  | 'ready'
  | 'running'
  | 'paused'
  | 'error'
  | 'stopped';

// 自主级别
export type AutonomyLevel = 'L0' | 'L1' | 'L2' | 'L3' | 'L4';

// Agent 角色
export type AgentRole = 'store_manager' | 'customer_service' | 'analyst';

// Agent
export interface Agent {
  id: number;
  name: string;
  role: AgentRole;
  avatar: string | null;
  description: string | null;
  status: AgentStatus;
  autonomy_level: AutonomyLevel;
  model: string | null;
  system_prompt_text: string | null;
  allowed_tools: string[];
  config: Record<string, unknown> | null;
  today_stats?: {
    messages: number;
    tool_calls: number;
    work_orders: number;
    tokens: number;
  };
  created_at: string;
  updated_at: string;
}

// 创建 Agent
export interface AgentCreate {
  name: string;
  role?: AgentRole;
  avatar?: string;
  autonomy_level?: AutonomyLevel;
  model?: string;
  system_prompt_text?: string;
  config?: Record<string, unknown>;
  allowed_tools?: string[];
}

// 会话
export interface AgentSession {
  id: number;
  title: string;
  session_type: string | null;
  status: 'active' | 'closed';
  message_count: number;
  created_at: string;
  updated_at: string;
}

// 消息
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  tool_calls?: ToolCall[];
  created_at: string;
}

// 工具调用
export interface ToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status: 'running' | 'success' | 'error';
  duration_ms?: number;
  error_message?: string;
}

// SSE 事件
export interface SseEvent {
  event: 'text' | 'tool_call' | 'tool_result' | 'done' | 'error';
  data: string;
}
