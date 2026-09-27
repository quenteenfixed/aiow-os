'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ArrowLeft } from 'lucide-react';

interface LoopRun {
  id: number;
  loop_id: number;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  error: string | null;
}

export default function LoopDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [loop, setLoop] = useState<any>(null);
  const [runs, setRuns] = useState<LoopRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [l, r] = await Promise.all([
          api.get<any>(`/loops/${id}`),
          api.get<{ items: LoopRun[] }>(`/loops/${id}/runs?page_size=10`).then((r) => r.items || []),
        ]);
        setLoop(l);
        setRuns(r);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const toggleStatus = async () => {
    if (!loop) return;
    setSubmitting(true);
    try {
      if (loop.status === 'running') {
        await api.post(`/loops/${id}/pause`);
        setLoop({ ...loop, status: 'paused' });
      } else {
        await api.post(`/loops/${id}/resume`);
        setLoop({ ...loop, status: 'running' });
      }
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!loop) return <div className="text-center py-20 text-muted-foreground">循环不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/loops" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回循环列表
      </a>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">{loop.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">#{loop.id} · OUPDEL 闭环</p>
        </div>
        <button onClick={toggleStatus} disabled={submitting}
          className={`px-4 py-2 rounded-md text-sm text-white disabled:opacity-50 ${loop.status === 'running' ? 'bg-orange-500' : 'bg-success'}`}>
          {loop.status === 'running' ? '暂停' : '恢复'}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">循环配置</h2>
          <div className="space-y-2 text-sm">
            <div><span className="text-muted-foreground">状态：</span>{loop.status}</div>
            <div><span className="text-muted-foreground">描述：</span>{loop.description || '-'}</div>
            {loop.cron_expr && <div><span className="text-muted-foreground">Cron：</span>{loop.cron_expr}</div>}
            {loop.config && (
              <div className="mt-3">
                <div className="text-muted-foreground mb-1">配置</div>
                <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">{JSON.stringify(loop.config, null, 2)}</pre>
              </div>
            )}
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">OUPDEL 阶段</h2>
          <div className="space-y-2">
            {['Observe 感知', 'Understand 理解', 'Plan 规划', 'Decide 决策', 'Execute 执行', 'Learn 学习'].map((stage, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs flex items-center justify-center font-medium">{i + 1}</div>
                <span className="text-sm">{stage}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4">执行记录</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="py-2 px-3">ID</th>
                <th className="py-2 px-3">状态</th>
                <th className="py-2 px-3">开始时间</th>
                <th className="py-2 px-3">耗时</th>
                <th className="py-2 px-3">错误</th>
              </tr>
            </thead>
            <tbody>
              {runs.length > 0 ? runs.map((r) => (
                <tr key={r.id} className="border-b border-border">
                  <td className="py-2 px-3">{r.id}</td>
                  <td className="py-2 px-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${r.status === 'success' ? 'bg-success/10 text-success' : r.status === 'running' ? 'bg-primary/10 text-primary' : 'bg-destructive/10 text-destructive'}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="py-2 px-3">{formatDate(r.started_at, 'MM-dd HH:mm:ss')}</td>
                  <td className="py-2 px-3">{r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '-'}</td>
                  <td className="py-2 px-3 text-destructive">{r.error || '-'}</td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="py-4 text-center text-muted-foreground">暂无执行记录</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
