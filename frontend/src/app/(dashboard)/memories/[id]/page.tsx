'use client';

import { useState, useEffect, Suspense } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { Memory } from '@/types';
import { ArrowLeft } from 'lucide-react';

const TYPE_LABEL: Record<string, string> = {
  fact: '事实', preference: '偏好', action: '行动', feedback: '反馈',
};
const SOURCE_LABEL: Record<string, string> = {
  manual: '手动', agent: 'Agent', loop: '循环', feedback: '反馈',
};

function MemoryDetailInner() {
  const params = useParams();
  const searchParams = useSearchParams();
  const id = Number(params.id);
  const agentId = searchParams.get('agent_id');
  const [memory, setMemory] = useState<Memory | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!agentId) return;
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<Memory>(`/memories/${id}?agent_id=${agentId}`);
        setMemory(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id, agentId]);

  if (!agentId) return <div className="text-center py-20 text-muted-foreground">缺少 agent_id 参数</div>;
  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!memory) return <div className="text-center py-20 text-muted-foreground">记忆不存在</div>;

  return (
    <div className="space-y-4">
      <a href={`/memories?agent_id=${agentId}`} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回记忆列表
      </a>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">{memory.title}</h1>
          <p className="text-sm text-muted-foreground mt-1">#{memory.id} · 创建于 {formatDate(memory.created_at, 'yyyy-MM-dd')}</p>
        </div>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-1 rounded bg-secondary">{TYPE_LABEL[memory.memory_type] || memory.memory_type}</span>
          <span className="text-xs px-2 py-1 rounded bg-secondary">{SOURCE_LABEL[memory.source] || memory.source}</span>
        </div>
      </div>

      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4">内容</h2>
        <p className="text-sm whitespace-pre-wrap">{memory.content}</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">重要性</div>
          <div className="text-xl font-bold text-warning">{'★'.repeat(memory.importance)}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">Agent</div>
          <div className="font-medium">#{memory.agent_id}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">过期时间</div>
          <div className="font-medium">{memory.expires_at ? formatDate(memory.expires_at, 'yyyy-MM-dd') : '永久'}</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-muted-foreground mb-1">更新时间</div>
          <div className="font-medium">{formatDate(memory.updated_at, 'MM-dd HH:mm')}</div>
        </div>
      </div>

      {memory.tags && memory.tags.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">标签</h2>
          <div className="flex flex-wrap gap-2">
            {memory.tags.map((t) => (
              <span key={t} className="text-xs px-2 py-1 rounded bg-secondary">{t}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function MemoryDetailPage() {
  return (
    <Suspense fallback={<div className="text-center py-20 text-muted-foreground">加载中...</div>}>
      <MemoryDetailInner />
    </Suspense>
  );
}
