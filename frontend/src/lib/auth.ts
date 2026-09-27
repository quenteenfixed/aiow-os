import { api } from './api';
import type { LoginRequest, LoginResponse, User, RefreshTokenResponse } from '@/types';

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_KEY = 'user';

export const auth = {
  // 登录
  async login(data: LoginRequest): Promise<LoginResponse> {
    const res = await api.post<LoginResponse>('/auth/login', data);
    if (res.access_token) {
      localStorage.setItem(ACCESS_TOKEN_KEY, res.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, res.refresh_token);
      localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    }
    return res;
  },

  // 登出
  logout() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  },

  // 获取当前用户
  getCurrentUser(): User | null {
    if (typeof window === 'undefined') return null;
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  },

  // 设置当前用户
  setCurrentUser(user: User) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },

  // 获取 Token
  getAccessToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },

  // 是否已登录
  isAuthenticated(): boolean {
    if (this.getAccessToken()) return true;
    // 后备：检查 cookie（中间件鉴权使用 cookie）
    if (typeof window !== 'undefined') {
      return document.cookie.includes('access_token=');
    }
    return false;
  },

  // 获取当前商户 ID
  getCurrentBusinessId(): string | null {
    const user = this.getCurrentUser();
    return user?.current_business_id ?? null;
  },
};
