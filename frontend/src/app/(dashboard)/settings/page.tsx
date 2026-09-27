'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import type { Business, BusinessStats } from '@/types';
import { useAuthStore } from '@/store/authStore';
import { Settings as SettingsIcon, Save } from 'lucide-react';

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const [business, setBusiness] = useState<Business | null>(null);
  const [stats, setStats] = useState<BusinessStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // 从用户信息中获取当前商户 ID
  const bizId = user?.current_business_id || user?.businesses?.[0]?.id;

  useEffect(() => {
    if (!bizId) {
      setLoading(false);
      return;
    }
    const fetchData = async () => {
      setLoading(true);
      try {
        const [b, s] = await Promise.all([
          api.get<Business>(`/businesses/${bizId}`),
          api.get<BusinessStats>(`/businesses/${bizId}/stats?period=today`),
        ]);
        setBusiness(b);
        setStats(s);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [bizId]);

  const handleSave = async () => {
    if (!business) return;
    setSaving(true);
    try {
      await api.put(`/businesses/${business.id}`, business);
      alert('保存成功');
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (loading || !business) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">商户设置</h1>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-xs text-muted-foreground">今日销售额</div>
            <div className="text-xl font-bold mt-1">{formatMoney(stats.total_sales)}</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-xs text-muted-foreground">今日订单</div>
            <div className="text-xl font-bold mt-1">{stats.total_orders}</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-xs text-muted-foreground">商品数</div>
            <div className="text-xl font-bold mt-1">{stats.product_count}</div>
          </div>
          <div className="bg-card border border-border rounded-lg p-4">
            <div className="text-xs text-muted-foreground">活跃告警</div>
            <div className="text-xl font-bold mt-1 text-warning">{stats.active_alerts}</div>
          </div>
        </div>
      )}

      <div className="bg-card border border-border rounded-lg p-6">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <SettingsIcon className="w-4 h-4" /> 基本信息
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="商户名称" value={business.name} onChange={(v) => setBusiness({ ...business, name: v })} />
          <Field label="行业分类" value={business.industry_category || ''} onChange={(v) => setBusiness({ ...business, industry_category: v })} />
          <Field label="经营模式" value={business.business_model || ''} onChange={(v) => setBusiness({ ...business, business_model: v })} />
          <Field label="时区" value={business.timezone} onChange={(v) => setBusiness({ ...business, timezone: v })} />
          <Field label="货币" value={business.currency} onChange={(v) => setBusiness({ ...business, currency: v })} />
          <Field label="城市" value={business.city || ''} onChange={(v) => setBusiness({ ...business, city: v })} />
        </div>
        <div className="mt-4">
          <button onClick={handleSave} disabled={saving} className="flex items-center gap-1 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            <Save className="w-4 h-4" /> {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
    </div>
  );
}
