'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { ArrowLeft } from 'lucide-react';

export default function ProductNewPage() {
  const router = useRouter();
  const [form, setForm] = useState({ name: '', description: '', category: '', brand: '', base_price: '', sku_code: '', price: '', stock_qty: '' });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const body: any = {
        name: form.name,
        description: form.description || undefined,
        category: form.category || undefined,
        brand: form.brand || undefined,
        base_price: Number(form.base_price) || 0,
        skus: form.sku_code ? [{
          sku_code: form.sku_code,
          price: Number(form.price) || Number(form.base_price) || 0,
          stock_qty: Number(form.stock_qty) || 0,
        }] : undefined,
      };
      const data = await api.post<{ id: string }>('/products', body);
      router.push(`/products/${data.id}`);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-4">
      <a href="/products" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回商品列表
      </a>
      <h1 className="text-xl font-bold">新建商品</h1>

      <form onSubmit={handleSubmit} className="bg-card border border-border rounded-lg p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">商品名称 <span className="text-destructive">*</span></label>
          <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="请输入商品名称" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">分类</label>
            <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="如：饮料" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">品牌</label>
            <input value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="如：可口可乐" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">基础价格</label>
          <input type="number" step="0.01" value={form.base_price} onChange={(e) => setForm({ ...form, base_price: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="0.00" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">描述</label>
          <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="商品描述" />
        </div>

        <div className="pt-4 border-t border-border">
          <h3 className="font-medium mb-3">SKU（可选，留空则自动生成默认 SKU）</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">SKU 编码</label>
              <input value={form.sku_code} onChange={(e) => setForm({ ...form, sku_code: e.target.value })}
                className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="SKU-001" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">售价</label>
              <input type="number" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })}
                className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="0.00" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">初始库存</label>
              <input type="number" value={form.stock_qty} onChange={(e) => setForm({ ...form, stock_qty: e.target.value })}
                className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="0" />
            </div>
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <button type="submit" disabled={submitting}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {submitting ? '提交中...' : '创建商品'}
          </button>
          <button type="button" onClick={() => router.back()}
            className="px-4 py-2 rounded-md border border-border hover:bg-secondary">取消</button>
        </div>
      </form>
    </div>
  );
}
