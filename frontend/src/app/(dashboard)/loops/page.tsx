'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatDate, formatRelativeTime } from '@/lib/format';
import { Play, Pause, RefreshCw } from 'lucide-react';

interface Loop {
  id: number;
  name: string;
  status: 'running' | 'paused';
  frequency: string;
  last_run_at: string | null;
  next_run_at: string | null;
  last_result: string | null;
}

export default function LoopsPage() {
  const [loops, setLoops] = useState<Loop[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: Loop[] }>('/loops');
        setLoops(data.items || []);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const togglePause = async (loop: Loop) => {
    try {
      if (loop.status === 'running') {
        await api.post(`/loops/${loop.id}/pause`);
      } else {
        await api.post(`/loops/${loop.id}/resume`);
      }
      setLoops(loops.map((l) => l.id === loop.id ? { ...l, status: l.status === 'running' ? 'paused' : 'running' } : l));
    } catch (err) {
      alert((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">OUPDEL 循环</h1>

      {loading ? (
        <div className="text-center py-20 text-muted-foreground">加载中...</div>
      ) : (
        <div className="space-y-3">
          {loops.map((loop) => (
            <div key={loop.id} className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{loop.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${loop.status === 'running' ? 'bg-success/10 text-success' : 'bg-gray-100 text-gray-500'}`}>
                      {loop.status === 'running' ? '运行中' : '已暂停'}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    频率: {loop.frequency} · 上次运行: {loop.last_run_at ? formatRelativeTime(loop.last_run_at) : '从未'}
                    {loop.next_run_at && ` · 下次运行: ${formatDate(loop.next_run_at, 'MM-dd HH:mm')}`}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Link href={`/loops/${loop.id}`} className="px-3 py-1.5 rounded-md border border-border text-sm hover:bg-secondary">详情</Link>
                  <button onClick={() => togglePause(loop)} className="px-3 py-1.5 rounded-md border border-border text-sm hover:bg-secondary flex items-center gap-1">
                    {loop.status === 'running' ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                    {loop.status === 'running' ? '暂停' : '恢复'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
