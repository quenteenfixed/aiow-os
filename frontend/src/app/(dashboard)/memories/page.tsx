'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatRelativeTime, truncate } from '@/lib/format';
import type { Memory, MemoryType, MemorySource } from '@/types';
import { Plus, Search } from 'lucide-react';

const TYPE_COLORS: Record<MemoryType, string> = {
  fact: 'bg-blue-100 text-blue-600',
  preference: 'bg-purple-100 text-purple-600',
  action: 'bg-green-100 text-green-600',
  feedback: 'bg-orange-100 text-orange-600',
};
const TYPE_LABELS: Record<MemoryType, string> = {
  fact: '事实', preference: '偏好', action: '行为', feedback: '反馈',
};

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [agents, setAgents] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentId, setAgentId] = useState<number | ''>('');
  const [type, setType] = useState('');
  const [query, setQuery] = useState('');

  useEffect(() => {
    api.get<{ items: { id: number; name: string }[] }>('/agents?page=1&page_size=50')
      .then((d) => setAgents(d.items || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!agentId) { setLoading(false); return; }
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: Memory[] }>(
          `/memories?agent_id=${agentId}&memory_type=${type}&page=1&page_size=50`,
        );
        setMemories(data.items);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [agentId, type]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">记忆管理</h1>
        {agentId && (
          <Link href={`/memories/new?agent_id=${agentId}`} className="flex items-center gap-1 bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm hover:opacity-90">
            <Plus className="w-4 h-4" /> 新增记忆
          </Link>
        )}
      </div>

      {/* Agent 选择 */}
      <div className="flex gap-3 flex-wrap">
        <select value={agentId} onChange={(e) => setAgentId(e.target.value ? Number(e.target.value) : '')} className="px-3 py-2 rounded-md border border-border text-sm">
          <option key="__placeholder__" value="">选择 Agent...</option>
          {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)} className="px-3 py-2 rounded-md border border-border text-sm">
          <option key="__placeholder__" value="">全部类型</option>
          {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {agentId && (
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索记忆..."
              className="w-full pl-9 pr-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
        )}
      </div>

      {!agentId ? (
        <div className="text-center py-20 text-muted-foreground">请先选择 Agent</div>
      ) : loading ? (
        <div className="text-center py-12 text-muted-foreground">加载中...</div>
      ) : memories.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">暂无记忆数据</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {memories.map((m) => (
            <Link key={m.id} href={`/memories/${m.id}?agent_id=${agentId}`} className="bg-card border border-border rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-2">
                <span className={`text-xs px-2 py-0.5 rounded ${TYPE_COLORS[m.memory_type]}`}>{TYPE_LABELS[m.memory_type]}</span>
                <span className="text-xs text-muted-foreground">{'★'.repeat(m.importance)}</span>
              </div>
              <div className="font-medium text-sm mb-1">{m.title}</div>
              <div className="text-xs text-muted-foreground line-clamp-2">{truncate(m.content, 80)}</div>
              <div className="text-xs text-muted-foreground mt-2">{formatRelativeTime(m.created_at)}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
