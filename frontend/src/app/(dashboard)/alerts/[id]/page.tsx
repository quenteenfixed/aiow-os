'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { Alert } from '@/types';
import { ArrowLeft } from 'lucide-react';

const LEVEL_COLOR: Record<string, string> = {
  P0: 'bg-destructive text-white', P1: 'bg-orange-500 text-white',
  P2: 'bg-warning text-white', P3: 'bg-blue-500 text-white',
};

export default function AlertDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [alertData, setAlertData] = useState<Alert | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<Alert>(`/alerts/${id}`);
        setAlertData(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const handleAction = async (action: string) => {
    setSubmitting(true);
    try {
      await api.post(`/alerts/${id}/${action}`);
      location.reload();
    } catch (err) {
      window.alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!alertData) return <div className="text-center py-20 text-muted-foreground">告警不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/alerts" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回告警列表
      </a>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">{alertData.title}</h1>
          <p className="text-sm text-muted-foreground mt-1">#{alertData.id} · {alertData.alert_type} · {formatDate(alertData.created_at)}</p>
        </div>
        <span className={`text-xs px-2 py-1 rounded font-medium ${LEVEL_COLOR[alertData.level] || ''}`}>{alertData.level}</span>
      </div>

      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4">告警内容</h2>
        <p className="text-sm whitespace-pre-wrap">{alertData.content}</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">来源</div>
          <div className="font-medium">{alertData.source}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">状态</div>
          <div className="font-medium">{alertData.status}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">确认时间</div>
          <div className="font-medium">{alertData.acknowledged_at ? formatDate(alertData.acknowledged_at, 'MM-dd HH:mm') : '-'}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">解决时间</div>
          <div className="font-medium">{alertData.resolved_at ? formatDate(alertData.resolved_at, 'MM-dd HH:mm') : '-'}</div>
        </div>
      </div>

      {alertData.metadata && Object.keys(alertData.metadata).length > 0 && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">元数据</h2>
          <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">{JSON.stringify(alertData.metadata, null, 2)}</pre>
        </div>
      )}

      {alertData.status === 'active' && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">处理操作</h2>
          <div className="flex gap-2">
            <button onClick={() => handleAction('acknowledge')} disabled={submitting}
              className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">确认告警</button>
            <button onClick={() => handleAction('resolve')} disabled={submitting}
              className="px-4 py-2 rounded-md bg-success text-white hover:opacity-90 disabled:opacity-50">标记已解决</button>
          </div>
        </div>
      )}
    </div>
  );
}
