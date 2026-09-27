'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import { ArrowLeft, Plus, Trash2 } from 'lucide-react';

interface SkuOption {
  id: string;
  sku_code: string;
  spec_name: string | null;
  price: number;
  stock_qty: number;
}

export default function OrderNewPage() {
  const router = useRouter();
  const [customerName, setCustomerName] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [items, setItems] = useState<{ sku_id: string; quantity: number; unit_price: number }[]>([
    { sku_id: '', quantity: 1, unit_price: 0 },
  ]);
  const [skus, setSkus] = useState<SkuOption[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get<{ items: SkuOption[] }>('/inventory?page_size=50').then((r) => setSkus(r.items || [])).catch(() => {});
  }, []);

  const total = items.reduce((sum, it) => sum + (it.unit_price * it.quantity), 0);

  const handleSkuChange = (idx: number, sku_id: string) => {
    const sku = skus.find((s) => s.id === sku_id);
    setItems(items.map((it, i) => i === idx ? { ...it, sku_id, unit_price: sku?.price || 0 } : it));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const validItems = items.filter((it) => it.sku_id && it.quantity > 0);
    if (validItems.length === 0) { alert('请至少添加一个商品'); return; }
    setSubmitting(true);
    try {
      const body: any = {
        items: validItems.map((it) => ({ sku_id: it.sku_id, qty: it.quantity, unit_price: it.unit_price })),
        customer_info: customerName ? { name: customerName, phone: customerPhone || '00000000000' } : undefined,
        source: 'manual',
      };
      const data = await api.post<{ id: string }>('/orders', body);
      router.push(`/orders/${data.id}`);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-4">
      <a href="/orders" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回订单列表
      </a>
      <h1 className="text-xl font-bold">新建订单</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="bg-card border border-border rounded-lg p-6">
          <h2 className="font-semibold mb-4">客户信息</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">客户姓名</label>
              <input value={customerName} onChange={(e) => setCustomerName(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="散客" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">联系电话</label>
              <input value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" placeholder="手机号" />
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">商品明细</h2>
            <button type="button" onClick={() => setItems([...items, { sku_id: '', quantity: 1, unit_price: 0 }])}
              className="flex items-center gap-1 text-sm text-primary hover:underline">
              <Plus className="w-4 h-4" /> 添加商品
            </button>
          </div>
          <div className="space-y-3">
            {items.map((it, idx) => (
              <div key={idx} className="grid grid-cols-12 gap-2 items-end">
                <div className="col-span-6">
                  <label className="block text-xs text-muted-foreground mb-1">商品 SKU</label>
                  <select value={it.sku_id} onChange={(e) => handleSkuChange(idx, e.target.value)}
                    className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary">
                    <option key="__placeholder__" value="">请选择</option>
                    {skus.map((s) => (
                      <option key={s.id} value={s.id}>{s.spec_name || s.sku_code} (库存: {s.stock_qty})</option>
                    ))}
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-muted-foreground mb-1">数量</label>
                  <input type="number" min="1" value={it.quantity} onChange={(e) => setItems(items.map((i, j) => j === idx ? { ...i, quantity: Number(e.target.value) } : i))}
                    className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div className="col-span-3">
                  <label className="block text-xs text-muted-foreground mb-1">单价</label>
                  <input type="number" step="0.01" value={it.unit_price} onChange={(e) => setItems(items.map((i, j) => j === idx ? { ...i, unit_price: Number(e.target.value) } : i))}
                    className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div className="col-span-1">
                  {items.length > 1 && (
                    <button type="button" onClick={() => setItems(items.filter((_, j) => j !== idx))}
                      className="p-2 text-destructive hover:bg-destructive/10 rounded-md">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-4 border-t border-border flex justify-between items-center">
            <span className="text-sm text-muted-foreground">合计</span>
            <span className="text-xl font-bold text-primary">{formatMoney(total)}</span>
          </div>
        </div>

        <div className="flex gap-2">
          <button type="submit" disabled={submitting}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {submitting ? '提交中...' : '创建订单'}
          </button>
          <button type="button" onClick={() => router.back()}
            className="px-4 py-2 rounded-md border border-border hover:bg-secondary">取消</button>
        </div>
      </form>
    </div>
  );
}
