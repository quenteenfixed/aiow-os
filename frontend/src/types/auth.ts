// 用户角色
export type UserRole = 'super_admin' | 'owner' | 'manager' | 'employee' | 'viewer' | 'agent';

// 用户信息
export interface User {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  avatar: string | null;
  status?: string;
  created_at?: string;
  businesses: BusinessBrief[];
  current_business_id: string | null;
}

// 商户简要信息
export interface BusinessBrief {
  id: string;
  name: string;
  slug?: string;
  category?: string;
  status?: string;
  role: UserRole;
}

// 登录请求
export interface LoginRequest {
  account: string;
  password: string;
}

// 登录响应
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

// 注册请求
export interface RegisterRequest {
  name: string;
  email?: string;
  phone?: string;
  password: string;
  confirm_password: string;
}

// 刷新 Token 响应
export interface RefreshTokenResponse {
  access_token: string;
  refresh_token: string;
}
