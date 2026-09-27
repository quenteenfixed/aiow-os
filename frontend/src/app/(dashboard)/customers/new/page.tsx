'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { ArrowLeft } from 'lucide-react';
import type { CustomerLevel } from '@/types';

export default function CustomerNewPage() {
  const router = useRouter();
  const [form, setForm] = useState({ name: '', phone: '', email: '', address: '', level: 'normal' as CustomerLevel, tags: '' });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const body: any = {
        name: form.name,
        phone: form.phone,
        email: form.email || undefined,
        address: form.address || undefined,
        level: form.level,
        tags: form.tags ? form.tags.split(',').map((t) => t.trim()).filter(Boolean) : undefined,
      };
      const data = await api.post<{ id: string }>('/customers', body);
      router.push(`/customers/${data.id}`);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-4">
      <a href="/customers" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回客户列表
      </a>
      <h1 className="text-xl font-bold">新建客户</h1>

      <form onSubmit={handleSubmit} className="bg-card border border-border rounded-lg p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">姓名 <span className="text-destructive">*</span></label>
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="客户姓名" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">电话 <span className="text-destructive">*</span></label>
            <input required value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="手机号" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">邮箱</label>
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="email@example.com" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">地址</label>
          <input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="收货地址" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">等级</label>
            <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value as CustomerLevel })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="normal">普通</option>
              <option value="vip">VIP</option>
              <option value="svip">SVIP</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">标签（逗号分隔）</label>
            <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="老客, 高价值" />
          </div>
        </div>
        <div className="flex gap-2 pt-2">
          <button type="submit" disabled={submitting}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {submitting ? '提交中...' : '创建客户'}
          </button>
          <button type="button" onClick={() => router.back()}
            className="px-4 py-2 rounded-md border border-border hover:bg-secondary">取消</button>
        </div>
      </form>
    </div>
  );
}
