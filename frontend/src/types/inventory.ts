// 库存状态
export type InventoryStatus = 'normal' | 'low' | 'out_of_stock' | 'overstock';

// 库存预警级别
export type InventoryAlertLevel = 'yellow' | 'orange' | 'red';

// 库存变动类型
export type InventoryChangeType = 'in' | 'out' | 'adjust' | 'check' | 'return';

// 库存项
export interface InventoryItem {
  sku_id: string;
  sku_code: string;
  product_name: string;
  spec_name: string | null;
  category: string | null;
  price: number;
  stock_qty: number;
  safety_stock: number;
  min_stock: number;
  status: InventoryStatus;
  last_in_time: string | null;
}

// 库存详情
export interface InventoryDetail {
  sku_id: string;
  product_id: string;
  sku_code: string;
  product_name: string;
  spec_name: string | null;
  category: string | null;
  price: number;
  cost_price: number | null;
  stock_qty: number;
  safety_stock: number;
  min_stock: number;
  stock_status: InventoryStatus;
  avg_daily_sales: number;
  days_of_stock: number | null;
  last_restocked_at: string | null;
  last_out_at: string | null;
  updated_at: string;
}

export interface SkuBrief {
  id: string;
  sku_code: string;
  spec_name: string | null;
  price: number;
  barcode: string | null;
}

export interface InventoryBatch {
  id: string;
  batch_no: string;
  quantity: number;
  expire_date: string | null;
  supplier: string | null;
}

// 库存流水
export interface InventoryLog {
  id: string;
  sku_code: string;
  product_name: string;
  change_type: InventoryChangeType;
  change_qty: number;
  before_qty: number;
  after_qty: number;
  reason: string | null;
  operator_type: 'user' | 'agent' | 'system';
  operator_name: string;
  created_at: string;
}

// 库存调整请求
export interface InventoryAdjustRequest {
  sku_id: string;
  change_type: 'in' | 'out' | 'adjust';
  change_qty: number;
  reason: string;
  batch_no?: string;
  expire_date?: string;
  supplier?: string;
}

// 库存预警
export interface InventoryAlert {
  sku_id: string;
  sku_code: string;
  product_name: string;
  stock_qty: number;
  safety_stock: number;
  min_stock: number;
  level: InventoryAlertLevel;
  days_of_stock: number;
}

// 临期商品
export interface ExpiringItem {
  sku_id: string;
  sku_code: string;
  product_name: string;
  batch_no: string;
  remaining_qty: number;
  expire_date: string;
  days_remaining: number;
}
