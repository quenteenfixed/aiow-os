'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { Product, ProductStatus } from '@/types';
import { Plus, Search, Package } from 'lucide-react';

const STATUS_MAP: Record<ProductStatus, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'bg-gray-100 text-gray-600' },
  active: { label: '上架', color: 'bg-success/10 text-success' },
  inactive: { label: '下架', color: 'bg-gray-100 text-gray-500' },
  archived: { label: '归档', color: 'bg-gray-100 text-gray-400' },
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: Product[]; total: number }>(
          `/products?keyword=${keyword}&status=${status}&page=${page}&page_size=20`,
        );
        setProducts(data.items);
        setTotal(data.total);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [keyword, status, page]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">商品管理</h1>
        <Link href="/products/new" className="flex items-center gap-1 bg-primary text-primary-foreground px-3 py-2 rounded-md text-sm hover:opacity-90">
          <Plus className="w-4 h-4" /> 新增商品
        </Link>
      </div>

      {/* 筛选 */}
      <div className="flex gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索商品名称..."
            className="w-full pl-9 pr-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-3 py-2 rounded-md border border-border text-sm">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="active">上架</option>
          <option value="inactive">下架</option>
          <option value="archived">归档</option>
        </select>
      </div>

      {/* 表格 */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-3 font-medium">商品</th>
              <th className="text-left px-4 py-3 font-medium">SKU数</th>
              <th className="text-left px-4 py-3 font-medium">基准价格</th>
              <th className="text-left px-4 py-3 font-medium">总库存</th>
              <th className="text-left px-4 py-3 font-medium">状态</th>
              <th className="text-left px-4 py-3 font-medium">更新时间</th>
              <th className="text-left px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">加载中...</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">暂无商品数据</td></tr>
            ) : (
              products.map((p) => (
                <tr key={p.id} className="border-t border-border hover:bg-secondary/50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {p.images?.[0] ? (
                        <img src={p.images[0]} alt={p.name} className="w-10 h-10 rounded object-cover" />
                      ) : (
                        <div className="w-10 h-10 rounded bg-secondary flex items-center justify-center">
                          <Package className="w-5 h-5 text-muted-foreground" />
                        </div>
                      )}
                      <div>
                        <div className="font-medium">{p.name}</div>
                        {p.category && <div className="text-xs text-muted-foreground">{p.category}</div>}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">{p.sku_count}</td>
                  <td className="px-4 py-3">{formatMoney(p.base_price)}</td>
                  <td className="px-4 py-3">{p.total_stock}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_MAP[p.status]?.color}`}>
                      {STATUS_MAP[p.status]?.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(p.updated_at, 'MM-dd HH:mm')}</td>
                  <td className="px-4 py-3">
                    <Link href={`/products/${p.id}`} className="text-primary hover:underline">详情</Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>共 {total} 条</span>
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-3 py-1 rounded border border-border disabled:opacity-50">上一页</button>
          <span>第 {page} 页</span>
          <button disabled={page * 20 >= total} onClick={() => setPage(page + 1)} className="px-3 py-1 rounded border border-border disabled:opacity-50">下一页</button>
        </div>
      </div>
    </div>
  );
}
