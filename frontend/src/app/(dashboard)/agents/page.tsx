'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { Agent, AgentStatus, AutonomyLevel } from '@/types';
import { Plus, MessageSquare, Settings } from 'lucide-react';

const STATUS_DOT: Record<AgentStatus, string> = {
  initializing: 'bg-gray-400',
  ready: 'bg-blue-500',
  running: 'bg-success',
  paused: 'bg-warning',
  error: 'bg-destructive',
  stopped: 'bg-gray-300',
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: Agent[] }>('/agents');
        setAgents(data.items || []);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Agent 管理</h1>
        <Link href="/agents/new" className="flex items-center gap-1 bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm hover:opacity-90">
          <Plus className="w-4 h-4" /> 新建 Agent
        </Link>
      </div>

      {loading ? (
        <div className="text-center py-20 text-muted-foreground">加载中...</div>
      ) : agents.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">暂无 Agent</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <div key={agent.id} className="bg-card border border-border rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-2xl">
                      🤖
                    </div>
                    <span className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white ${STATUS_DOT[agent.status]}`} />
                  </div>
                  <div>
                    <div className="font-semibold">{agent.name}</div>
                    <div className="text-xs text-muted-foreground">{agent.role}</div>
                  </div>
                </div>
                <span className="text-xs px-2 py-0.5 rounded bg-accent/10 text-accent font-medium">{agent.autonomy_level}</span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground mb-3">
                <div>消息数：<span className="text-foreground font-medium">{agent.today_stats?.messages ?? 0}</span></div>
                <div>工具调用：<span className="text-foreground font-medium">{agent.today_stats?.tool_calls ?? 0}</span></div>
                <div>工单数：<span className="text-foreground font-medium">{agent.today_stats?.work_orders ?? 0}</span></div>
                <div>Token：<span className="text-foreground font-medium">{agent.today_stats?.tokens ?? 0}</span></div>
              </div>

              <div className="flex gap-2">
                <Link href={`/agents/${agent.id}/chat`} className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-md bg-primary text-primary-foreground text-xs hover:opacity-90">
                  <MessageSquare className="w-3.5 h-3.5" /> 对话
                </Link>
                <Link href={`/agents/${agent.id}`} className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-md border border-border text-xs hover:bg-secondary">
                  <Settings className="w-3.5 h-3.5" /> 配置
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
