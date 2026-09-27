'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { Customer } from '@/types';
import { Search, Plus, User } from 'lucide-react';

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: Customer[] }>(`/customers?keyword=${keyword}&page=1&page_size=50`);
        setCustomers(data.items);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [keyword]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">客户管理</h1>
        <Link href="/customers/new" className="flex items-center gap-1 bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm hover:opacity-90">
          <Plus className="w-4 h-4" /> 新增客户
        </Link>
      </div>

      <div className="relative max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索姓名/手机号..."
          className="w-full pl-9 pr-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-3 font-medium">客户</th>
              <th className="text-left px-4 py-3 font-medium">手机号</th>
              <th className="text-left px-4 py-3 font-medium">等级</th>
              <th className="text-left px-4 py-3 font-medium">累计消费</th>
              <th className="text-left px-4 py-3 font-medium">订单数</th>
              <th className="text-left px-4 py-3 font-medium">注册时间</th>
              <th className="text-left px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">加载中...</td></tr>
            ) : customers.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">暂无客户数据</td></tr>
            ) : (
              customers.map((c) => (
                <tr key={c.id} className="border-t border-border hover:bg-secondary/50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
                        <User className="w-4 h-4 text-muted-foreground" />
                      </div>
                      <span className="font-medium">{c.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">{c.phone}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${c.level === 'svip' ? 'bg-accent/10 text-accent' : c.level === 'vip' ? 'bg-warning/10 text-warning' : 'bg-gray-100 text-gray-600'}`}>
                      {c.level}
                    </span>
                  </td>
                  <td className="px-4 py-3">{formatMoney(c.total_spent)}</td>
                  <td className="px-4 py-3">{c.order_count}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(c.created_at, 'MM-dd')}</td>
                  <td className="px-4 py-3">
                    <Link href={`/customers/${c.id}`} className="text-primary hover:underline">详情</Link>
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
