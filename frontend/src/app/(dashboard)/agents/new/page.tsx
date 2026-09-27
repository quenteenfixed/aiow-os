'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { ArrowLeft } from 'lucide-react';
import type { AgentRole, AutonomyLevel } from '@/types';

export default function AgentNewPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: '', role: 'store_manager' as AgentRole, autonomy_level: 'L2' as AutonomyLevel,
    model: '', system_prompt_text: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const body: any = {
        name: form.name,
        role: form.role,
        autonomy_level: form.autonomy_level,
        model: form.model || undefined,
        system_prompt_text: form.system_prompt_text || undefined,
      };
      const data = await api.post<{ id: number }>('/agents', body);
      router.push(`/agents/${data.id}`);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-4">
      <a href="/agents" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回 Agent 列表
      </a>
      <h1 className="text-xl font-bold">新建 Agent</h1>

      <form onSubmit={handleSubmit} className="bg-card border border-border rounded-lg p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">名称 <span className="text-destructive">*</span></label>
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="如：店长小助手" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">角色</label>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as AgentRole })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="store_manager">店长</option>
              <option value="customer_service">客服</option>
              <option value="analyst">分析师</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">自主级别</label>
            <select value={form.autonomy_level} onChange={(e) => setForm({ ...form, autonomy_level: e.target.value as AutonomyLevel })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="L0">L0 - 仅建议</option>
              <option value="L1">L1 - 低风险自执行</option>
              <option value="L2">L2 - 需审批</option>
              <option value="L3">L3 - 高自主</option>
              <option value="L4">L4 - 全自动</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">模型</label>
            <input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="如：gpt-4o" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">System Prompt</label>
          <textarea rows={6} value={form.system_prompt_text} onChange={(e) => setForm({ ...form, system_prompt_text: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary font-mono"
            placeholder="你是一个零售店智能助手，负责..." />
        </div>
        <div className="flex gap-2 pt-2">
          <button type="submit" disabled={submitting}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {submitting ? '提交中...' : '创建 Agent'}
          </button>
          <button type="button" onClick={() => router.back()}
            className="px-4 py-2 rounded-md border border-border hover:bg-secondary">取消</button>
        </div>
      </form>
    </div>
  );
}
