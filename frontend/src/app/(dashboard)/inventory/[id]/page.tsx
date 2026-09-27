'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import type { InventoryDetail } from '@/types';
import { ArrowLeft } from 'lucide-react';

export default function InventoryDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [detail, setDetail] = useState<InventoryDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<InventoryDetail>(`/inventory/${id}`);
        setDetail(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!detail) return <div className="text-center py-20 text-muted-foreground">库存记录不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/inventory" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回库存列表
      </a>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">{detail.spec_name || detail.sku_code}</h1>
          <p className="text-sm text-muted-foreground mt-1">SKU: {detail.sku_id} · 商品: {detail.product_name}</p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-secondary">{detail.stock_status}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-2xl font-bold">{detail.stock_qty}</div>
          <div className="text-xs text-muted-foreground">当前库存</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-2xl font-bold">{detail.safety_stock}</div>
          <div className="text-xs text-muted-foreground">安全库存</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-2xl font-bold">{formatMoney(detail.price || 0)}</div>
          <div className="text-xs text-muted-foreground">售价</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="text-2xl font-bold">{detail.days_of_stock ?? '-'}</div>
          <div className="text-xs text-muted-foreground">可售天数</div>
        </div>
      </div>

      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4">SKU 信息</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div><span className="text-muted-foreground">SKU 编码：</span>{detail.sku_code}</div>
          <div><span className="text-muted-foreground">分类：</span>{detail.category || '-'}</div>
          <div><span className="text-muted-foreground">成本价：</span>{formatMoney(detail.cost_price ?? 0)}</div>
          <div><span className="text-muted-foreground">最小库存：</span>{detail.min_stock}</div>
          <div><span className="text-muted-foreground">日均销量：</span>{detail.avg_daily_sales}</div>
          <div><span className="text-muted-foreground">库存状态：</span>{detail.stock_status}</div>
        </div>
      </div>
    </div>
  );
}
