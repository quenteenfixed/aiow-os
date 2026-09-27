'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { Zap, AlertTriangle, Shield } from 'lucide-react';

interface CircuitStatus {
  status: 'normal' | 'triggered';
  reason: string | null;
  triggered_at: string | null;
}

export default function CircuitBreakerPage() {
  const [status, setStatus] = useState<CircuitStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = async () => {
    try {
      const data = await api.get<CircuitStatus>('/circuit-breaker/status');
      setStatus(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStatus(); }, []);

  const handleRecover = async () => {
    const reason = prompt('请输入恢复原因:');
    if (!reason) return;
    try {
      await api.post('/circuit-breaker/recover', { reason });
      fetchStatus();
    } catch (err) { alert((err as Error).message); }
  };

  const handleTrigger = async () => {
    if (!confirm('确认手动触发熔断？这将禁止所有 Agent 自动操作。')) return;
    try {
      await api.post('/circuit-breaker/trigger', { reason: '手动触发' });
      fetchStatus();
    } catch (err) { alert((err as Error).message); }
  };

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;

  const isTriggered = status?.status === 'triggered';

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">熔断管理</h1>

      <div className={`bg-card border rounded-lg p-8 text-center ${isTriggered ? 'border-destructive' : 'border-border'}`}>
        <div className={`text-6xl mb-4 ${isTriggered ? 'animate-pulse' : ''}`}>
          {isTriggered ? <AlertTriangle className="w-16 h-16 text-destructive mx-auto" /> : <Shield className="w-16 h-16 text-success mx-auto" />}
        </div>
        <div className={`text-2xl font-bold mb-2 ${isTriggered ? 'text-destructive' : 'text-success'}`}>
          {isTriggered ? '系统已熔断' : '系统运行正常'}
        </div>
        {isTriggered && (
          <div className="text-muted-foreground mb-4">
            <p>原因：{status?.reason}</p>
            <p>触发时间：{status?.triggered_at ? formatDate(status.triggered_at) : '-'}</p>
          </div>
        )}
        <div className="flex justify-center gap-3 mt-6">
          {isTriggered ? (
            <button onClick={handleRecover} className="px-6 py-2 rounded-md bg-success text-white hover:opacity-90">
              恢复系统
            </button>
          ) : (
            <button onClick={handleTrigger} className="px-6 py-2 rounded-md bg-destructive text-destructive-foreground hover:opacity-90">
              手动触发熔断
            </button>
          )}
        </div>
      </div>

      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-3">影响范围</h2>
        <ul className="text-sm text-muted-foreground space-y-1">
          <li>• 熔断期间，所有 Agent 自动操作被禁止</li>
          <li>• 工单审批和执行暂停</li>
          <li>• 已在执行的操作可能被中断</li>
          <li>• 手动操作（库存调整、订单处理）仍可进行</li>
        </ul>
      </div>
    </div>
  );
}
