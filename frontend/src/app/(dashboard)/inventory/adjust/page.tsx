'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { Scan, Package } from 'lucide-react';

export default function InventoryAdjustPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    sku_id: '',
    change_type: 'in' as 'in' | 'out' | 'adjust',
    change_qty: 0,
    reason: '',
    batch_no: '',
    expire_date: '',
    supplier: '',
  });
  const [scanMode, setScanMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleScan = () => {
    // 使用 Barcode Detection API 或提示输入
    const code = prompt('请扫描或输入 SKU 编码:');
    if (code) {
      setForm({ ...form, sku_id: code });
      setScanMode(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.sku_id || !form.change_qty || !form.reason) {
      alert('请填写必填项');
      return;
    }
    setSubmitting(true);
    try {
      const data: Record<string, unknown> = {
        sku_id: form.sku_id,
        change_type: form.change_type,
        change_qty: form.change_type === 'out' ? -Math.abs(form.change_qty) : form.change_qty,
        reason: form.reason,
      };
      if (form.change_type === 'in' && form.batch_no) data.batch_no = form.batch_no;
      if (form.expire_date) data.expire_date = form.expire_date;
      if (form.supplier) data.supplier = form.supplier;

      const result = await api.post('/inventory/adjust', data);
      if ((result as any)?.status === 'pending_approval') {
        alert('已提交，等待审批');
      } else {
        alert('操作成功');
      }
      router.push('/inventory');
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <h1 className="text-xl font-bold">库存调整</h1>

      <form onSubmit={handleSubmit} className="bg-card border border-border rounded-lg p-6 space-y-4">
        {/* SKU 选择 - 支持扫码 */}
        <div>
          <label className="block text-sm font-medium mb-1">SKU <span className="text-destructive">*</span></label>
          <div className="flex gap-2">
            <input
              value={form.sku_id}
              onChange={(e) => setForm({ ...form, sku_id: e.target.value })}
              placeholder="输入或扫描 SKU 编码"
              className="flex-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <button type="button" onClick={handleScan} className="flex items-center gap-1 px-3 py-2 rounded-md border border-border text-sm hover:bg-secondary">
              <Scan className="w-4 h-4" /> 扫码
            </button>
          </div>
        </div>

        {/* 变动类型 */}
        <div>
          <label className="block text-sm font-medium mb-1">变动类型 <span className="text-destructive">*</span></label>
          <div className="flex gap-2">
            {[
              { v: 'in', l: '入库' },
              { v: 'out', l: '出库' },
              { v: 'adjust', l: '调整' },
            ].map((t) => (
              <button key={t.v} type="button" onClick={() => setForm({ ...form, change_type: t.v as any })}
                className={`flex-1 py-2 rounded-md text-sm ${form.change_type === t.v ? 'bg-primary text-primary-foreground' : 'border border-border hover:bg-secondary'}`}>
                {t.l}
              </button>
            ))}
          </div>
        </div>

        {/* 数量 */}
        <div>
          <label className="block text-sm font-medium mb-1">变动数量 <span className="text-destructive">*</span></label>
          <input type="number" value={form.change_qty || ''} onChange={(e) => setForm({ ...form, change_qty: Number(e.target.value) })}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
        </div>

        {/* 原因 */}
        <div>
          <label className="block text-sm font-medium mb-1">变动原因 <span className="text-destructive">*</span></label>
          <textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} rows={3}
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
        </div>

        {/* 入库附加信息 */}
        {form.change_type === 'in' && (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">批次号</label>
              <input value={form.batch_no} onChange={(e) => setForm({ ...form, batch_no: e.target.value })}
                className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">过期日期</label>
                <input type="date" value={form.expire_date} onChange={(e) => setForm({ ...form, expire_date: e.target.value })}
                  className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">供应商</label>
                <input value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })}
                  className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
            </div>
          </>
        )}

        <button type="submit" disabled={submitting} className="w-full py-2 rounded-md bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-50">
          {submitting ? '提交中...' : '提交'}
        </button>
      </form>
    </div>
  );
}
