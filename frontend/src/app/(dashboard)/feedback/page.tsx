'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { BarChart3 } from 'lucide-react';

export default function FeedbackPage() {
  const [agents, setAgents] = useState<{ id: number; name: string }[]>([]);
  const [agentId, setAgentId] = useState<number | ''>('');
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get<{ items: { id: number; name: string }[] }>('/agents?page=1&page_size=50')
      .then((d) => setAgents(d.items || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!agentId) return;
    setLoading(true);
    api.get(`/feedback/stats?agent_id=${agentId}&days=30`)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, [agentId]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">反馈学习</h1>

      <div className="flex items-center gap-3">
        <label className="text-sm font-medium">选择 Agent:</label>
        <select value={agentId} onChange={(e) => setAgentId(e.target.value ? Number(e.target.value) : '')}
          className="px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary">
          <option key="__placeholder__" value="">请选择 Agent...</option>
          {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>

      {!agentId ? (
        <div className="text-center py-20 text-muted-foreground">请先选择 Agent 查看反馈统计</div>
      ) : loading ? (
        <div className="text-center py-20 text-muted-foreground">加载中...</div>
      ) : (
        <>
          <div className="bg-card border border-border rounded-lg p-6">
            <h2 className="font-semibold mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Agent 决策质量
            </h2>
            {stats ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Stat label="平均批准率" value={stats.approval_rate ? `${(stats.approval_rate * 100).toFixed(1)}%` : '-'} />
                <Stat label="执行成功率" value={stats.execution_success_rate ? `${(stats.execution_success_rate * 100).toFixed(1)}%` : '-'} />
                <Stat label="总工单数" value={stats.total_work_orders ?? '-'} />
              </div>
            ) : (
              <div className="text-muted-foreground">暂无统计数据</div>
            )}
          </div>

          <div className="bg-card border border-border rounded-lg p-6">
            <h2 className="font-semibold mb-4">反馈学习闭环</h2>
            <div className="space-y-3">
              {['反馈来源', '反馈分析', '策略调整', '效果验证', '记忆沉淀'].map((step, i) => (
                <div key={step} className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium">{i + 1}</div>
                  <span className="text-sm">{step}</span>
                  {i < 4 && <div className="flex-1 border-t border-border ml-2" />}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted rounded-lg p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </div>
  );
}
