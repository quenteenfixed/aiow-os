// 客户等级
export type CustomerLevel = 'normal' | 'vip' | 'svip';

// 客户
export interface Customer {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  address: string | null;
  level: CustomerLevel;
  tags: string[];
  total_spent: number;
  order_count: number;
  created_at: string;
}

// 创建/编辑客户
export interface CustomerCreate {
  name: string;
  phone: string;
  email?: string;
  address?: string;
  level?: CustomerLevel;
  tags?: string[];
}
