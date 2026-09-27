'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import type { LoginResponse } from '@/types';

export default function RegisterPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // 已登录则跳转
  useEffect(() => {
    if (isAuthenticated) {
      router.replace('/');
    }
  }, [isAuthenticated, router]);
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm_password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const validatePassword = (pwd: string): string | null => {
    if (pwd.length < 8) return '密码至少 8 位';
    if (pwd.length > 32) return '密码最多 32 位';
    const hasAlpha = /[a-zA-Z]/.test(pwd);
    const hasDigit = /\d/.test(pwd);
    if (!hasAlpha || !hasDigit) return '密码需同时包含字母和数字';
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== form.confirm_password) {
      setError('两次输入的密码不一致');
      return;
    }
    const pwdErr = validatePassword(form.password);
    if (pwdErr) {
      setError(pwdErr);
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await api.post<LoginResponse>('/auth/register', {
        name: form.name,
        email: form.email,
        password: form.password,
      });
      login(res);
      router.replace('/');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md">
      <div className="bg-card border border-border rounded-xl shadow-lg p-8">
        <div className="text-center mb-8">
          <div className="text-4xl mb-2">🤖</div>
          <h1 className="text-2xl font-bold text-foreground">创建账号</h1>
          <p className="text-sm text-muted-foreground mt-1">加入 AIOW 自运转零售店</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium mb-1">姓名</label>
            <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border focus:outline-none focus:ring-2 focus:ring-primary" required />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">邮箱</label>
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border focus:outline-none focus:ring-2 focus:ring-primary" required />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">密码</label>
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border focus:outline-none focus:ring-2 focus:ring-primary" required minLength={8} maxLength={32} />
            <p className="text-xs text-muted-foreground mt-1">8-32 位，需同时包含字母和数字</p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">确认密码</label>
            <input type="password" value={form.confirm_password} onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
              className="w-full px-3 py-2 rounded-md border border-border focus:outline-none focus:ring-2 focus:ring-primary" required minLength={8} maxLength={32} />
          </div>

          <button type="submit" disabled={loading}
            className="w-full py-2 rounded-md bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-50">
            {loading ? '注册中...' : '注册'}
          </button>
        </form>

        <p className="text-center text-sm text-muted-foreground mt-6">
          已有账号？{' '}
          <Link href="/login" className="text-primary hover:underline">立即登录</Link>
        </p>
      </div>
    </div>
  );
}
