'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { Product } from '@/types';
import { ArrowLeft } from 'lucide-react';

export default function ProductDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<Product>(`/products/${id}`);
        setProduct(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!product) return <div className="text-center py-20 text-muted-foreground">商品不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/products" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回商品列表
      </a>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">{product.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">ID: {product.id} · 创建于 {formatDate(product.created_at, 'yyyy-MM-dd')}</p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-secondary">{product.status}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-lg p-5 lg:col-span-2">
          <h2 className="font-semibold mb-4">商品信息</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-muted-foreground">分类：</span>{product.category || '-'}</div>
            <div><span className="text-muted-foreground">品牌：</span>{product.brand || '-'}</div>
            <div><span className="text-muted-foreground">基础价格：</span>{formatMoney(product.base_price)}</div>
            <div><span className="text-muted-foreground">总库存：</span>{product.total_stock}</div>
            <div><span className="text-muted-foreground">SKU 数量：</span>{product.sku_count}</div>
            <div><span className="text-muted-foreground">排序：</span>{product.sort_order}</div>
          </div>
          {product.description && (
            <div className="mt-4 pt-4 border-t border-border">
              <div className="text-sm text-muted-foreground mb-1">描述</div>
              <p className="text-sm">{product.description}</p>
            </div>
          )}
          {product.tags && product.tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1">
              {product.tags.map((t) => (
                <span key={t} className="text-xs px-2 py-0.5 rounded bg-secondary">{t}</span>
              ))}
            </div>
          )}
        </div>

        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">SKU 列表</h2>
          <div className="space-y-2">
            {product.skus && product.skus.length > 0 ? product.skus.map((sku) => (
              <div key={sku.id} className="p-3 rounded-md border border-border">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{sku.spec_name || '默认规格'}</span>
                  <span className="text-muted-foreground text-xs">{sku.sku_code}</span>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  售价 {formatMoney(sku.price)} · 库存 {sku.stock_qty} · 安全库存 {sku.safety_stock}
                </div>
                {sku.barcode && <div className="text-xs text-muted-foreground">条码: {sku.barcode}</div>}
              </div>
            )) : <div className="text-sm text-muted-foreground">暂无 SKU</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
