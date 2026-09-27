'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { WorkOrder, WorkOrderStatus, WorkOrderType, RiskLevel } from '@/types';

const TYPE_LABELS: Record<WorkOrderType, string> = {
  price_adjust: '调价', stock_in: '入库', stock_out: '出库', refund: '退款', purchase_suggestion: '采购建议',
};
const TYPE_COLORS: Record<WorkOrderType, string> = {
  price_adjust: 'bg-blue-100 text-blue-600',
  stock_in: 'bg-green-100 text-green-600',
  stock_out: 'bg-orange-100 text-orange-600',
  refund: 'bg-red-100 text-red-600',
  purchase_suggestion: 'bg-purple-100 text-purple-600',
};
const RISK_COLORS: Record<RiskLevel, string> = {
  low: 'bg-success/10 text-success', medium: 'bg-warning/10 text-warning', high: 'bg-destructive/10 text-destructive',
};
const STATUS_COLORS: Record<WorkOrderStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-700', approved: 'bg-blue-100 text-blue-600', rejected: 'bg-red-100 text-red-600',
  executing: 'bg-purple-100 text-purple-600', completed: 'bg-green-100 text-green-700', failed: 'bg-red-100 text-red-700', cancelled: 'bg-gray-100 text-gray-500',
};

export default function WorkOrdersPage() {
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('all');
  const [status, setStatus] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const url = status ? `/work-orders?status=${status}&page=1&page_size=20` : '/work-orders?page=1&page_size=20';
        const data = await api.get<{ items: WorkOrder[] }>(url);
        setOrders(data.items);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [status]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">工单审批</h1>

      <div className="flex gap-2 border-b border-border">
        {[
          { key: 'all', label: '全部' },
          { key: 'pending', label: '待审批' },
          { key: 'approved', label: '已批准' },
          { key: 'executing', label: '执行中' },
          { key: 'completed', label: '已完成' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setStatus(t.key === 'all' ? '' : t.key); }}
            className={`px-4 py-2 text-sm border-b-2 -mb-px ${tab === t.key ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-3 font-medium">工单号</th>
              <th className="text-left px-4 py-3 font-medium">类型</th>
              <th className="text-left px-4 py-3 font-medium">标题</th>
              <th className="text-left px-4 py-3 font-medium">风险</th>
              <th className="text-left px-4 py-3 font-medium">状态</th>
              <th className="text-left px-4 py-3 font-medium">发起Agent</th>
              <th className="text-left px-4 py-3 font-medium">创建时间</th>
              <th className="text-left px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">加载中...</td></tr>
            ) : orders.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-muted-foreground">暂无工单</td></tr>
            ) : (
              orders.map((wo) => (
                <tr key={wo.id} className="border-t border-border hover:bg-secondary/50">
                  <td className="px-4 py-3 font-mono text-xs">#{wo.id}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${TYPE_COLORS[wo.order_type]}`}>{TYPE_LABELS[wo.order_type]}</span>
                  </td>
                  <td className="px-4 py-3 font-medium">{wo.title}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${RISK_COLORS[wo.risk_level]}`}>{wo.risk_level}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[wo.status]}`}>{wo.status}</span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{wo.agent_name || '-'}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(wo.created_at, 'MM-dd HH:mm')}</td>
                  <td className="px-4 py-3">
                    <Link href={`/work-orders/${wo.id}`} className="text-primary hover:underline">详情</Link>
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
