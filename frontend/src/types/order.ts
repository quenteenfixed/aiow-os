// 订单状态
export type OrderStatus =
  | 'pending'
  | 'confirmed'
  | 'paid'
  | 'preparing'
  | 'shipped'
  | 'delivered'
  | 'completed'
  | 'cancelled'
  | 'refunded';

// 支付状态
export type PaymentStatus = 'unpaid' | 'partial' | 'paid' | 'refunded';

// 订单来源
export type OrderSource = 'manual' | 'a2a' | 'pos';

// 支付方式
export type PaymentMethod = 'wechat' | 'alipay' | 'cash' | 'card';

// 订单项
export interface OrderItem {
  id: string;
  sku_id: string;
  sku_code: string;
  product_name: string;
  spec_name: string | null;
  unit_price: number;
  quantity: number;
  subtotal: number;
}

// 订单
export interface Order {
  id: string;
  order_no: string;
  status: OrderStatus;
  source: OrderSource;
  payment_status: PaymentStatus;
  payment_method: PaymentMethod | null;
  customer_name: string | null;
  customer_phone: string | null;
  item_count: number;
  total_amount: number;
  discount_amount: number;
  payable_amount: number;
  paid_amount: number;
  remark: string | null;
  shipping_address: Record<string, unknown> | null;
  created_at: string;
  paid_at: string | null;
  shipped_at: string | null;
  completed_at: string | null;
  items?: OrderItem[];
}

// 创建订单请求
export interface CreateOrderRequest {
  items: Array<{
    sku_id: string;
    quantity: number;
    unit_price?: number;
  }>;
  customer_id?: string;
  shipping_address?: Record<string, unknown>;
  remark?: string;
}

// 支付请求
export interface PayOrderRequest {
  payment_method: PaymentMethod;
}

// 发货请求
export interface ShipOrderRequest {
  shipping_company: string;
  tracking_no: string;
}

// 退款请求
export interface RefundRequest {
  amount: number;
  reason: string;
  type: 'full' | 'partial';
}

// 订单统计
export interface OrderStats {
  total_count: number;
  total_amount: number;
  avg_order_value: number;
  completed_count: number;
  cancelled_count: number;
  refunded_count: number;
  refunded_amount: number;
}
