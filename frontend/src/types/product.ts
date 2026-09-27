// 商品状态
export type ProductStatus = 'draft' | 'active' | 'inactive' | 'archived';

// SKU
export interface Sku {
  id: string;
  sku_code: string;
  spec_name: string | null;
  price: number;
  cost_price: number | null;
  original_price: number | null;
  barcode: string | null;
  weight: number | null;
  image: string | null;
  stock_qty: number;
  safety_stock: number;
  min_stock: number;
  status: 'active' | 'inactive';
}

// 商品 (SPU)
export interface Product {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  brand: string | null;
  images: string[];
  tags: string[];
  base_price: number;
  sort_order: number;
  status: ProductStatus;
  sku_count: number;
  total_stock: number;
  created_at: string;
  updated_at: string;
  skus?: Sku[];
}

// 创建商品请求
export interface ProductCreate {
  name: string;
  description?: string;
  category?: string;
  brand?: string;
  images?: string[];
  tags?: string[];
  base_price: number;
  sort_order?: number;
  skus?: Array<{
    sku_code: string;
    spec_name?: string;
    price: number;
    cost_price?: number;
    original_price?: number;
    barcode?: string;
    weight?: number;
    image?: string;
    stock_qty?: number;
    safety_stock?: number;
    min_stock?: number;
  }>;
}
