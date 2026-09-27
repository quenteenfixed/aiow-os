// 记忆类型
export type MemoryType = 'fact' | 'preference' | 'action' | 'feedback';

// 记忆来源
export type MemorySource = 'manual' | 'agent' | 'loop' | 'feedback';

// 记忆
export interface Memory {
  id: number;
  agent_id: number;
  memory_type: MemoryType;
  title: string;
  content: string;
  tags: string[];
  importance: number; // 1-5
  source: MemorySource;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

// 创建记忆
export interface MemoryCreate {
  memory_type?: MemoryType;
  title: string;
  content: string;
  tags?: string[];
  importance?: number;
  source?: MemorySource;
  ttl_hours?: number;
}

// 记忆统计
export interface MemoryStats {
  total: number;
  by_type: Record<MemoryType, number>;
  by_source: Record<MemorySource, number>;
  by_importance: Record<number, number>;
  expiring_count: number;
}
