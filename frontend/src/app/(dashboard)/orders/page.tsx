'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { Order, OrderStatus } from '@/types';
import { Search, Plus } from 'lucide-react';

const STATUS_COLORS: Record<OrderStatus, string> = {
  pending: 'bg-gray-100 text-gray-600',
  confirmed: 'bg-blue-100 text-blue-600',
  paid: 'bg-green-100 text-green-600',
  preparing: 'bg-yellow-100 text-yellow-600',
  shipped: 'bg-purple-100 text-purple-600',
  delivered: 'bg-indigo-100 text-indigo-600',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-400',
  refunded: 'bg-red-100 text-red-600',
};

const STATUS_LABELS: Record<OrderStatus, string> = {
  pending: '待确认', confirmed: '已确认', paid: '已支付', preparing: '备货中',
  shipped: '已发货', delivered: '已送达', completed: '已完成', cancelled: '已取消', refunded: '已退款',
};

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: Order[] }>(
          `/orders?order_no=${keyword}&status=${status}&page=1&page_size=20`,
        );
        setOrders(data.items);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [keyword, status]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">订单管理</h1>
        <Link href="/orders/new" className="flex items-center gap-1 bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm hover:opacity-90">
          <Plus className="w-4 h-4" /> 创建订单
        </Link>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索订单号..."
            className="w-full pl-9 pr-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-3 py-2 rounded-md border border-border text-sm">
          <option key="__placeholder__" value="">全部状态</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-3 font-medium">订单号</th>
              <th className="text-left px-4 py-3 font-medium">客户</th>
              <th className="text-left px-4 py-3 font-medium">商品数</th>
              <th className="text-left px-4 py-3 font-medium">金额</th>
              <th className="text-left px-4 py-3 font-medium">状态</th>
              <th className="text-left px-4 py-3 font-medium">来源</th>
              <th className="text-left px-4 py-3 font-medium">下单时间</th>
              <th className="text-left px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">加载中...</td></tr>
            ) : orders.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">暂无订单数据</td></tr>
            ) : (
              orders.map((o) => (
                <tr key={o.id} className="border-t border-border hover:bg-secondary/50">
                  <td className="px-4 py-3 font-mono text-xs">{o.order_no}</td>
                  <td className="px-4 py-3">{o.customer_name || '散客'}</td>
                  <td className="px-4 py-3">{o.item_count}</td>
                  <td className="px-4 py-3 font-medium">{formatMoney(o.payable_amount)}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[o.status]}`}>
                      {STATUS_LABELS[o.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{o.source}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(o.created_at, 'MM-dd HH:mm')}</td>
                  <td className="px-4 py-3">
                    <Link href={`/orders/${o.id}`} className="text-primary hover:underline">详情</Link>
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
