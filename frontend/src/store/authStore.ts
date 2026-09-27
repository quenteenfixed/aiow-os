import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '@/types';
import { auth } from '@/lib/auth';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (data: { access_token: string; refresh_token: string; user: User }) => void;
  logout: () => void;
  setUser: (user: User) => void;
  setCurrentBusiness: (businessId: string) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: auth.getCurrentUser(),
      accessToken: auth.getAccessToken(),
      isAuthenticated: auth.isAuthenticated(),
      login: ({ access_token, refresh_token, user }) => {
        if (typeof window !== 'undefined') {
          localStorage.setItem('access_token', access_token);
          localStorage.setItem('refresh_token', refresh_token);
          localStorage.setItem('user', JSON.stringify(user));
          // 同步写入 cookie，供服务端中间件鉴权使用
          document.cookie = `access_token=${access_token}; path=/; max-age=${7 * 24 * 3600}; SameSite=Lax`;
        }
        set({ user, accessToken: access_token, isAuthenticated: true });
      },
      logout: () => {
        auth.logout();
        if (typeof window !== 'undefined') {
          document.cookie = 'access_token=; path=/; max-age=0; SameSite=Lax';
        }
        set({ user: null, accessToken: null, isAuthenticated: false });
      },
      setUser: (user) => {
        auth.setCurrentUser(user);
        set({ user });
      },
      setCurrentBusiness: (businessId) => {
        set((state) => ({
          user: state.user ? { ...state.user, current_business_id: businessId } : null,
        }));
      },
    }),
    {
      name: 'aiow-auth',
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
    },
  ),
);
