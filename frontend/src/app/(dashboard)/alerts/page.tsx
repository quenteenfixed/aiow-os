'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatDate, formatRelativeTime } from '@/lib/format';
import type { Alert, AlertLevel } from '@/types';

const LEVEL_COLORS: Record<AlertLevel, string> = {
  P0: 'bg-destructive text-white', P1: 'bg-orange-500 text-white', P2: 'bg-warning text-white', P3: 'bg-blue-500 text-white',
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [level, setLevel] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: Alert[] }>(
          `/alerts?status=active&level=${level}&page=1&page_size=50`,
        );
        setAlerts(data.items);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [level]);

  const handleAck = async (id: number) => {
    try {
      await api.post(`/alerts/${id}/acknowledge`);
      setAlerts(alerts.filter((a) => a.id !== id));
    } catch (err) {
      alert((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">告警中心</h1>

      {/* 级别筛选 */}
      <div className="flex gap-2">
        <button onClick={() => setLevel('')} className={`px-3 py-1.5 rounded text-sm ${!level ? 'bg-primary text-primary-foreground' : 'bg-secondary'}`}>全部</button>
        {(['P0', 'P1', 'P2', 'P3'] as AlertLevel[]).map((l) => (
          <button key={l} onClick={() => setLevel(l)} className={`px-3 py-1.5 rounded text-sm ${level === l ? LEVEL_COLORS[l] : 'bg-secondary'}`}>
            {l}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {loading ? (
          <div className="text-center py-12 text-muted-foreground">加载中...</div>
        ) : alerts.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">暂无活跃告警</div>
        ) : (
          alerts.map((a) => (
            <div key={a.id} className={`bg-card border ${a.level === 'P0' ? 'border-destructive' : 'border-border'} rounded-lg p-4`}>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span className={`text-xs px-2 py-0.5 rounded font-bold ${LEVEL_COLORS[a.level]}`}>{a.level}</span>
                  <div>
                    <div className="font-medium">{a.title}</div>
                    <div className="text-sm text-muted-foreground mt-0.5">{a.content}</div>
                    <div className="text-xs text-muted-foreground mt-1">
                      来源: {a.source} · {formatRelativeTime(a.created_at)}
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleAck(a.id)} className="px-3 py-1 text-sm rounded border border-border hover:bg-secondary">
                    确认
                  </button>
                  <Link href={`/alerts/${a.id}`} className="px-3 py-1 text-sm rounded bg-primary text-primary-foreground hover:opacity-90">
                    详情
                  </Link>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
