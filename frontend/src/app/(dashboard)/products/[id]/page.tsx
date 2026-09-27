'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { Product } from '@/types';
import { ArrowLeft, Pencil, Plus } from 'lucide-react';

export default function ProductDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showAddSku, setShowAddSku] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', category: '', brand: '', base_price: 0, description: '' });
  const [skuForm, setSkuForm] = useState({ sku_code: '', spec_name: '', price: 0, cost_price: 0, safety_stock: 0 });

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await api.get<Product>(`/products/${id}`);
      setProduct(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [id]);

  const handlePublish = async (publish: boolean) => {
    setSubmitting(true);
    try {
      await api.post(`/products/${id}/${publish ? 'publish' : 'unpublish'}`, publish ? {} : { reason: '手动下架' });
      fetchData();
    } catch (err) { alert((err as Error).message); }
    finally { setSubmitting(false); }
  };

  const handleSaveEdit = async () => {
    setSubmitting(true);
    try {
      await api.put(`/products/${id}`, editForm);
      setShowEdit(false);
      fetchData();
    } catch (err) { alert((err as Error).message); }
    finally { setSubmitting(false); }
  };

  const handleAddSku = async () => {
    setSubmitting(true);
    try {
      await api.post(`/products/${id}/skus`, skuForm);
      setShowAddSku(false);
      setSkuForm({ sku_code: '', spec_name: '', price: 0, cost_price: 0, safety_stock: 0 });
      fetchData();
    } catch (err) { alert((err as Error).message); }
    finally { setSubmitting(false); }
  };

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!product) return <div className="text-center py-20 text-muted-foreground">商品不存在</div>;

  const isDraft = product.status === 'draft';

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
        <div className="flex items-center gap-2">
          <span className="text-xs px-2 py-1 rounded bg-secondary">{product.status}</span>
          <button onClick={() => { setEditForm({ name: product.name, category: product.category || '', brand: product.brand || '', base_price: product.base_price, description: product.description || '' }); setShowEdit(true); }}
            className="flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-secondary">
            <Pencil className="w-3.5 h-3.5" /> 编辑
          </button>
          {isDraft ? (
            <button onClick={() => handlePublish(true)} disabled={submitting}
              className="px-3 py-1.5 rounded-md bg-success text-white text-sm hover:opacity-90 disabled:opacity-50">上架</button>
          ) : (
            <button onClick={() => handlePublish(false)} disabled={submitting}
              className="px-3 py-1.5 rounded-md bg-destructive text-destructive-foreground text-sm hover:opacity-90 disabled:opacity-50">下架</button>
          )}
        </div>
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
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">SKU 列表</h2>
            <button onClick={() => setShowAddSku(true)}
              className="flex items-center gap-1 px-2 py-1 rounded-md bg-primary text-primary-foreground text-xs hover:opacity-90">
              <Plus className="w-3 h-3" /> 新增 SKU
            </button>
          </div>
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

      {/* 编辑商品弹窗 */}
      {showEdit && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-lg p-6 w-full max-w-md space-y-4">
            <h3 className="font-semibold text-lg">编辑商品</h3>
            <div>
              <label className="text-sm text-muted-foreground">名称</label>
              <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-muted-foreground">分类</label>
                <input value={editForm.category} onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                  className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
              <div>
                <label className="text-sm text-muted-foreground">品牌</label>
                <input value={editForm.brand} onChange={(e) => setEditForm({ ...editForm, brand: e.target.value })}
                  className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
            </div>
            <div>
              <label className="text-sm text-muted-foreground">基础价格</label>
              <input type="number" step="0.01" value={editForm.base_price} onChange={(e) => setEditForm({ ...editForm, base_price: Number(e.target.value) })}
                className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">描述</label>
              <textarea value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={3}
                className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowEdit(false)} className="px-4 py-2 rounded-md border border-border text-sm hover:bg-secondary">取消</button>
              <button onClick={handleSaveEdit} disabled={submitting} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:opacity-90 disabled:opacity-50">保存</button>
            </div>
          </div>
        </div>
      )}

      {/* 新增 SKU 弹窗 */}
      {showAddSku && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-lg p-6 w-full max-w-md space-y-4">
            <h3 className="font-semibold text-lg">新增 SKU</h3>
            <div>
              <label className="text-sm text-muted-foreground">SKU 编码（留空自动生成）</label>
              <input value={skuForm.sku_code} onChange={(e) => setSkuForm({ ...skuForm, sku_code: e.target.value })} placeholder="如：LARGE-001"
                className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">规格名称</label>
              <input value={skuForm.spec_name} onChange={(e) => setSkuForm({ ...skuForm, spec_name: e.target.value })} placeholder="如：大号、红色"
                className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-muted-foreground">售价</label>
                <input type="number" step="0.01" value={skuForm.price} onChange={(e) => setSkuForm({ ...skuForm, price: Number(e.target.value) })}
                  className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
              <div>
                <label className="text-sm text-muted-foreground">成本价</label>
                <input type="number" step="0.01" value={skuForm.cost_price} onChange={(e) => setSkuForm({ ...skuForm, cost_price: Number(e.target.value) })}
                  className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              </div>
            </div>
            <div>
              <label className="text-sm text-muted-foreground">安全库存</label>
              <input type="number" value={skuForm.safety_stock} onChange={(e) => setSkuForm({ ...skuForm, safety_stock: Number(e.target.value) })}
                className="w-full mt-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowAddSku(false)} className="px-4 py-2 rounded-md border border-border text-sm hover:bg-secondary">取消</button>
              <button onClick={handleAddSku} disabled={submitting} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:opacity-90 disabled:opacity-50">创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
