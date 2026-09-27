'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { Agent, AgentSession } from '@/types';
import { ArrowLeft, MessageSquare } from 'lucide-react';

const STATUS_LABEL: Record<string, string> = {
  initializing: '初始化', ready: '就绪', running: '运行中',
  paused: '已暂停', error: '错误', stopped: '已停止',
};

export default function AgentDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [a, s] = await Promise.all([
          api.get<Agent>(`/agents/${id}`),
          api.get<{ items: AgentSession[] }>(`/agents/${id}/sessions?page_size=10`).then((r) => r.items || []),
        ]);
        setAgent(a);
        setSessions(s);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!agent) return <div className="text-center py-20 text-muted-foreground">Agent 不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/agents" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回 Agent 列表
      </a>

      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-lg font-medium">
            {agent.avatar || agent.name[0]}
          </div>
          <div>
            <h1 className="text-xl font-bold">{agent.name}</h1>
            <p className="text-sm text-muted-foreground">{agent.role} · {agent.autonomy_level}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-1 rounded bg-secondary h-fit">{STATUS_LABEL[agent.status] || agent.status}</span>
          <Link href={`/agents/${id}/chat`} className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:opacity-90">
            <MessageSquare className="w-4 h-4" /> 对话
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-lg p-5 lg:col-span-2">
          <h2 className="font-semibold mb-4">基本信息</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-muted-foreground">模型：</span>{agent.model || '-'}</div>
            <div><span className="text-muted-foreground">角色：</span>{agent.role}</div>
            <div><span className="text-muted-foreground">自主级别：</span>{agent.autonomy_level}</div>
            <div><span className="text-muted-foreground">状态：</span>{STATUS_LABEL[agent.status] || agent.status}</div>
          </div>
          {agent.description && (
            <div className="mt-4 pt-4 border-t border-border">
              <div className="text-sm text-muted-foreground mb-1">描述</div>
              <p className="text-sm">{agent.description}</p>
            </div>
          )}
          {agent.system_prompt_text && (
            <div className="mt-4 pt-4 border-t border-border">
              <div className="text-sm text-muted-foreground mb-1">System Prompt</div>
              <pre className="text-xs bg-muted p-3 rounded overflow-x-auto whitespace-pre-wrap">{agent.system_prompt_text}</pre>
            </div>
          )}
        </div>

        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">今日统计</h2>
          {agent.today_stats ? (
            <div className="grid grid-cols-2 gap-3">
              <div><div className="text-xl font-bold">{agent.today_stats.messages}</div><div className="text-xs text-muted-foreground">消息数</div></div>
              <div><div className="text-xl font-bold">{agent.today_stats.tool_calls}</div><div className="text-xs text-muted-foreground">工具调用</div></div>
              <div><div className="text-xl font-bold">{agent.today_stats.work_orders}</div><div className="text-xs text-muted-foreground">工单</div></div>
              <div><div className="text-xl font-bold">{agent.today_stats.tokens}</div><div className="text-xs text-muted-foreground">Tokens</div></div>
            </div>
          ) : <div className="text-sm text-muted-foreground">暂无统计</div>}
        </div>
      </div>

      {agent.allowed_tools && agent.allowed_tools.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">允许工具</h2>
          <div className="flex flex-wrap gap-2">
            {agent.allowed_tools.map((t) => (
              <span key={t} className="text-xs px-2 py-1 rounded bg-secondary">{t}</span>
            ))}
          </div>
        </div>
      )}

      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4">最近会话</h2>
        <div className="space-y-2">
          {sessions.length > 0 ? sessions.map((s) => (
            <Link key={s.id} href={`/agents/${id}/chat`} className="flex items-center justify-between p-3 rounded-md border border-border hover:bg-secondary">
              <span className="text-sm font-medium">{s.title}</span>
              <span className="text-xs text-muted-foreground">{s.message_count} 条消息 · {formatDate(s.updated_at, 'MM-dd HH:mm')}</span>
            </Link>
          )) : <div className="text-sm text-muted-foreground">暂无会话</div>}
        </div>
      </div>
    </div>
  );
}
