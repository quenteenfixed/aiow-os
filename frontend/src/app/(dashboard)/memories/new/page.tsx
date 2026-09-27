'use client';

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { ArrowLeft } from 'lucide-react';
import type { MemoryType } from '@/types';

function MemoryNewInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const agentId = searchParams.get('agent_id');
  const [form, setForm] = useState({
    title: '', content: '', memory_type: 'fact' as MemoryType,
    importance: 3, tags: '', ttl_hours: '',
  });
  const [submitting, setSubmitting] = useState(false);

  if (!agentId) {
    return <div className="text-center py-20 text-muted-foreground">缺少 agent_id 参数，请从记忆列表进入</div>;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const body: any = {
        title: form.title,
        content: form.content,
        memory_type: form.memory_type,
        importance: Number(form.importance),
        tags: form.tags ? form.tags.split(',').map((t) => t.trim()).filter(Boolean) : undefined,
        ttl_hours: form.ttl_hours ? Number(form.ttl_hours) : undefined,
      };
      const data = await api.post<{ id: number }>(`/memories?agent_id=${agentId}`, body);
      router.push(`/memories/${data.id}?agent_id=${agentId}`);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-4">
      <a href={`/memories?agent_id=${agentId}`} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回记忆列表
      </a>
      <h1 className="text-xl font-bold">新建记忆</h1>

      <form onSubmit={handleSubmit} className="bg-card border border-border rounded-lg p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">标题 <span className="text-destructive">*</span></label>
          <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="记忆标题" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">类型</label>
            <select value={form.memory_type} onChange={(e) => setForm({ ...form, memory_type: e.target.value as MemoryType })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="fact">事实</option>
              <option value="preference">偏好</option>
              <option value="action">行动</option>
              <option value="feedback">反馈</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">重要性 (1-5)</label>
            <input type="number" min="1" max="5" value={form.importance} onChange={(e) => setForm({ ...form, importance: Number(e.target.value) })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">内容 <span className="text-destructive">*</span></label>
          <textarea required rows={5} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="记忆内容" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">标签（逗号分隔）</label>
            <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="商品, 价格" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">过期时间（小时，留空永久）</label>
            <input type="number" value={form.ttl_hours} onChange={(e) => setForm({ ...form, ttl_hours: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="如：72" />
          </div>
        </div>
        <div className="flex gap-2 pt-2">
          <button type="submit" disabled={submitting}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {submitting ? '提交中...' : '创建记忆'}
          </button>
          <button type="button" onClick={() => router.back()}
            className="px-4 py-2 rounded-md border border-border hover:bg-secondary">取消</button>
        </div>
      </form>
    </div>
  );
}

export default function MemoryNewPage() {
  return (
    <Suspense fallback={<div className="text-center py-20 text-muted-foreground">加载中...</div>}>
      <MemoryNewInner />
    </Suspense>
  );
}
