'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { InventoryItem, InventoryStatus } from '@/types';
import { Search, Plus } from 'lucide-react';

const STATUS_MAP: Record<InventoryStatus, { label: string; color: string }> = {
  normal: { label: '正常', color: 'bg-success/10 text-success' },
  low: { label: '低库存', color: 'bg-warning/10 text-warning' },
  out_of_stock: { label: '缺货', color: 'bg-destructive/10 text-destructive' },
  overstock: { label: '积压', color: 'bg-blue-500/10 text-blue-500' },
};

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: InventoryItem[] }>(
          `/inventory?keyword=${keyword}&status=${status}&page=1&page_size=50`,
        );
        setItems(data.items);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [keyword, status]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">库存管理</h1>
        <div className="flex gap-2">
          <Link href="/inventory/alerts" className="px-3 py-2 rounded-md border border-border text-sm hover:bg-secondary">库存预警</Link>
          <Link href="/inventory/stocktake" className="px-3 py-2 rounded-md border border-border text-sm hover:bg-secondary">盘点</Link>
          <Link href="/inventory/adjust" className="flex items-center gap-1 bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm hover:opacity-90">
            <Plus className="w-4 h-4" /> 库存调整
          </Link>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索商品名/SKU编码..."
            className="w-full pl-9 pr-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-3 py-2 rounded-md border border-border text-sm">
          <option value="">全部状态</option>
          <option value="normal">正常</option>
          <option value="low">低库存</option>
          <option value="out_of_stock">缺货</option>
          <option value="overstock">积压</option>
        </select>
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-3 font-medium">SKU编码</th>
              <th className="text-left px-4 py-3 font-medium">商品名称</th>
              <th className="text-left px-4 py-3 font-medium">单价</th>
              <th className="text-left px-4 py-3 font-medium">当前库存</th>
              <th className="text-left px-4 py-3 font-medium">安全库存</th>
              <th className="text-left px-4 py-3 font-medium">状态</th>
              <th className="text-left px-4 py-3 font-medium">最后入库</th>
              <th className="text-left px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">加载中...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">暂无库存数据</td></tr>
            ) : (
              items.map((item) => (
                <tr key={item.sku_id} className="border-t border-border hover:bg-secondary/50">
                  <td className="px-4 py-3 font-mono text-xs">{item.sku_code}</td>
                  <td className="px-4 py-3">{item.product_name}{item.spec_name && <span className="text-muted-foreground"> / {item.spec_name}</span>}</td>
                  <td className="px-4 py-3">{formatMoney(item.price)}</td>
                  <td className="px-4 py-3 font-medium">{item.stock_qty}</td>
                  <td className="px-4 py-3 text-muted-foreground">{item.safety_stock}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_MAP[item.status]?.color}`}>
                      {STATUS_MAP[item.status]?.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{item.last_in_time ? formatDate(item.last_in_time, 'MM-dd') : '-'}</td>
                  <td className="px-4 py-3">
                    <Link href={`/inventory/${item.sku_id}`} className="text-primary hover:underline">详情</Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
