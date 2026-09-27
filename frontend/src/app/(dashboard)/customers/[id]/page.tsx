'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { Customer } from '@/types';
import { ArrowLeft } from 'lucide-react';

const LEVEL_LABEL: Record<string, string> = { normal: '普通', vip: 'VIP', svip: 'SVIP' };

export default function CustomerDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<Customer>(`/customers/${id}`);
        setCustomer(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!customer) return <div className="text-center py-20 text-muted-foreground">客户不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/customers" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回客户列表
      </a>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">{customer.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">ID: {customer.id}</p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-secondary">{LEVEL_LABEL[customer.level] || customer.level}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-lg p-5 lg:col-span-2">
          <h2 className="font-semibold mb-4">基本信息</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-muted-foreground">电话：</span>{customer.phone}</div>
            <div><span className="text-muted-foreground">邮箱：</span>{customer.email || '-'}</div>
            <div className="col-span-2"><span className="text-muted-foreground">地址：</span>{customer.address || '-'}</div>
            <div><span className="text-muted-foreground">注册时间：</span>{formatDate(customer.created_at, 'yyyy-MM-dd')}</div>
          </div>
          {customer.tags && customer.tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1">
              {customer.tags.map((t) => (
                <span key={t} className="text-xs px-2 py-0.5 rounded bg-secondary">{t}</span>
              ))}
            </div>
          )}
        </div>

        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">消费统计</h2>
          <div className="space-y-3">
            <div>
              <div className="text-2xl font-bold text-primary">{formatMoney(customer.total_spent)}</div>
              <div className="text-xs text-muted-foreground">累计消费</div>
            </div>
            <div>
              <div className="text-2xl font-bold">{customer.order_count}</div>
              <div className="text-xs text-muted-foreground">订单数</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
