// 商户
export interface Business {
  id: number;
  name: string;
  industry_category: string | null;
  industry_subcategory: string | null;
  business_model: string | null;
  address: string | null;
  city: string | null;
  province: string | null;
  country: string | null;
  timezone: string;
  currency: string;
  config: Record<string, unknown> | null;
}

// 商户统计
export interface BusinessStats {
  total_sales: number;
  total_orders: number;
  avg_order_value: number;
  inventory_alerts: number;
  pending_work_orders: number;
  active_alerts: number;
  product_count: number;
  sku_count: number;
}
