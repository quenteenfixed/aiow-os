'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { Order, OrderStatus, PaymentMethod } from '@/types';
import { ArrowLeft } from 'lucide-react';

const STATUS_LABEL: Record<OrderStatus, string> = {
  pending: '待确认', confirmed: '已确认', paid: '已支付',
  preparing: '备货中', shipped: '已发货', delivered: '已送达',
  completed: '已完成', cancelled: '已取消', refunded: '已退款',
};

export default function OrderDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [payMethod, setPayMethod] = useState<PaymentMethod>('wechat');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<Order>(`/orders/${id}`);
        setOrder(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const handleAction = async (action: string, body?: unknown) => {
    setSubmitting(true);
    try {
      await api.post(`/orders/${id}/${action}`, body);
      location.reload();
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!order) return <div className="text-center py-20 text-muted-foreground">订单不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/orders" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回订单列表
      </a>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">订单 {order.order_no}</h1>
          <p className="text-sm text-muted-foreground mt-1">下单时间 {formatDate(order.created_at)}</p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-secondary">{STATUS_LABEL[order.status] || order.status}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-lg p-5 lg:col-span-2">
          <h2 className="font-semibold mb-4">商品明细</h2>
          <div className="space-y-2">
            {order.items && order.items.length > 0 ? order.items.map((item) => (
              <div key={item.id} className="flex items-center justify-between p-3 rounded-md border border-border">
                <div>
                  <div className="text-sm font-medium">{item.product_name}</div>
                  <div className="text-xs text-muted-foreground">{item.spec_name || item.sku_code}</div>
                </div>
                <div className="text-right text-sm">
                  <div>{formatMoney(item.unit_price)} × {item.quantity}</div>
                  <div className="font-medium">{formatMoney(item.subtotal)}</div>
                </div>
              </div>
            )) : <div className="text-sm text-muted-foreground">暂无商品</div>}
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-card border border-border rounded-lg p-5">
            <h2 className="font-semibold mb-4">金额</h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-muted-foreground">商品总额</span><span>{formatMoney(order.total_amount)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">优惠</span><span>-{formatMoney(order.discount_amount)}</span></div>
              <div className="flex justify-between font-medium pt-2 border-t border-border">
                <span>应付</span><span className="text-primary">{formatMoney(order.payable_amount)}</span>
              </div>
              <div className="flex justify-between"><span className="text-muted-foreground">已付</span><span>{formatMoney(order.paid_amount)}</span></div>
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-5">
            <h2 className="font-semibold mb-4">客户</h2>
            <div className="space-y-1 text-sm">
              <div><span className="text-muted-foreground">姓名：</span>{order.customer_name || '-'}</div>
              <div><span className="text-muted-foreground">电话：</span>{order.customer_phone || '-'}</div>
              <div><span className="text-muted-foreground">来源：</span>{order.source}</div>
            </div>
          </div>
        </div>
      </div>

      {/* 操作按钮 */}
      {order.status === 'pending' && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">订单操作</h2>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => handleAction('confirm')} disabled={submitting}
              className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">确认订单</button>
            <button onClick={() => handleAction('cancel', { reason: '用户取消' })} disabled={submitting}
              className="px-4 py-2 rounded-md border border-border hover:bg-secondary disabled:opacity-50">取消订单</button>
          </div>
        </div>
      )}

      {order.status === 'confirmed' && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">支付订单</h2>
          <div className="flex items-center gap-3 mb-4">
            <select value={payMethod} onChange={(e) => setPayMethod(e.target.value as PaymentMethod)}
              className="px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="wechat">微信支付</option>
              <option value="alipay">支付宝</option>
              <option value="cash">现金</option>
              <option value="card">银行卡</option>
            </select>
            <button onClick={() => handleAction('pay', { payment_method: payMethod })} disabled={submitting}
              className="px-4 py-2 rounded-md bg-success text-white hover:opacity-90 disabled:opacity-50">确认支付</button>
          </div>
        </div>
      )}

      {order.status === 'paid' && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">发货</h2>
          <button onClick={() => handleAction('ship', { shipping_company: '顺丰', tracking_no: Date.now().toString() })} disabled={submitting}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">模拟发货</button>
        </div>
      )}

      {order.status === 'shipped' && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">签收确认</h2>
          <button onClick={() => handleAction('complete')} disabled={submitting}
            className="px-4 py-2 rounded-md bg-success text-white hover:opacity-90 disabled:opacity-50">确认签收并完成订单</button>
        </div>
      )}

      {(order.status === 'paid' || order.status === 'completed') && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">售后</h2>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => handleAction('refund', { refund_amount: order.payable_amount, refund_reason: '客户申请退款', refund_type: 'full' })} disabled={submitting}
              className="px-4 py-2 rounded-md border border-border text-sm hover:bg-secondary disabled:opacity-50">全额退款</button>
          </div>
        </div>
      )}

      {order.remark && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-2">备注</h2>
          <p className="text-sm">{order.remark}</p>
        </div>
      )}
    </div>
  );
}
