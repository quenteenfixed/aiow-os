'use client';

import { useState, useEffect } from 'react';
import { useCircuitStore } from '@/store/uiStore';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';

interface CircuitStatus {
  status: 'normal' | 'triggered';
  reason: string | null;
  triggered_at: string | null;
}

export default function CircuitBreakerBar() {
  const { isTriggered, reason, triggeredAt, setTriggered, setNormal } = useCircuitStore();
  const [recovering, setRecovering] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // 轮询熔断状态
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await api.get<CircuitStatus>('/circuit-breaker/status');
        if (data.status === 'triggered') {
          setTriggered(data.reason || '系统异常', data.triggered_at || new Date().toISOString());
        } else {
          setNormal();
        }
      } catch {
        // 忽略错误
      }
    };
    fetchStatus();
    const timer = setInterval(fetchStatus, 10000);
    return () => clearInterval(timer);
  }, [setTriggered, setNormal]);

  const handleRecover = async () => {
    setRecovering(true);
    try {
      await api.post('/circuit-breaker/recover', { reason: '手动恢复' });
      setNormal();
      setShowConfirm(false);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setRecovering(false);
    }
  };

  if (!isTriggered) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-destructive text-destructive-foreground px-4 py-2 flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <span className="text-lg">⚠️</span>
        <span className="font-medium">系统已熔断</span>
        {reason && <span className="opacity-80">| 原因：{reason}</span>}
        {triggeredAt && (
          <span className="opacity-80">| 触发时间：{formatDate(triggeredAt)}</span>
        )}
      </div>
      <button
        onClick={() => setShowConfirm(true)}
        disabled={recovering}
        className="bg-white text-destructive px-3 py-1 rounded font-medium hover:bg-gray-100 disabled:opacity-50"
      >
        {recovering ? '恢复中...' : '一键恢复'}
      </button>

      {showConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white text-foreground rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">确认恢复系统</h3>
            <p className="text-muted-foreground mb-4">
              恢复后，Agent 将恢复自动操作。请确认已排查熔断原因。
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowConfirm(false)}
                className="px-4 py-2 rounded border hover:bg-secondary"
              >
                取消
              </button>
              <button
                onClick={handleRecover}
                className="px-4 py-2 rounded bg-destructive text-destructive-foreground hover:opacity-90"
              >
                确认恢复
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
