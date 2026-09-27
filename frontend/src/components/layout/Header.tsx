'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { useUIStore, useNotificationStore } from '@/store/uiStore';
import { usePermission } from '@/hooks/usePermission';
import { Search, Bell, Menu, LogOut, User, ChevronDown } from 'lucide-react';

export default function Header() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { toggleSidebar } = useUIStore();
  const { items, unreadCount, markAllAsRead } = useNotificationStore();
  const { hasPermission } = usePermission();
  const [searchOpen, setSearchOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [mounted, setMounted] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  // 延迟挂载，避免 SSR/CSR 因持久化 store 导致 hydration 不一致
  useEffect(() => {
    setMounted(true);
  }, []);

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setSearchOpen(false);
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // 快捷键
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggleSidebar]);

  return (
    <header className="h-14 bg-card border-b border-border flex items-center justify-between px-4 sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <button onClick={toggleSidebar} className="p-1 hover:bg-secondary rounded">
          <Menu className="w-5 h-5" />
        </button>
        <div ref={searchRef} className="relative">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-secondary w-64 cursor-text"
               onClick={() => setSearchOpen(true)}>
            <Search className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">全局搜索... (⌘K)</span>
          </div>
          {searchOpen && (
            <div className="absolute top-full mt-2 left-0 w-80 bg-card border border-border rounded-lg shadow-lg p-2">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索商品、订单、客户、工单..."
                className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="mt-2 text-xs text-muted-foreground px-2">
                输入关键词搜索，回车跳转
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* 通知 */}
        <div ref={notifRef} className="relative">
          <button onClick={() => setNotifOpen(!notifOpen)} className="relative p-1 hover:bg-secondary rounded">
            <Bell className="w-5 h-5" />
            {mounted && unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 bg-destructive text-destructive-foreground text-xs rounded-full w-4 h-4 flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </button>
          {notifOpen && (
            <div className="absolute right-0 top-full mt-2 w-80 bg-card border border-border rounded-lg shadow-lg">
              <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                <span className="font-medium text-sm">通知</span>
                <button onClick={markAllAsRead} className="text-xs text-primary hover:underline">
                  全部已读
                </button>
              </div>
              <div className="max-h-80 overflow-y-auto">
                {items.length === 0 ? (
                  <div className="p-4 text-center text-sm text-muted-foreground">暂无通知</div>
                ) : (
                  items.slice(0, 10).map((item) => (
                    <Link
                      key={item.id}
                      href={item.link || '#'}
                      onClick={() => setNotifOpen(false)}
                      className={`block px-3 py-2 hover:bg-secondary border-b border-border ${!item.read ? 'bg-secondary/50' : ''}`}
                    >
                      <div className="text-sm font-medium">{item.title}</div>
                      <div className="text-xs text-muted-foreground truncate">{item.message}</div>
                    </Link>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* 用户菜单 */}
        <div ref={userRef} className="relative">
          <button onClick={() => setUserMenuOpen(!userMenuOpen)} className="flex items-center gap-2 p-1 hover:bg-secondary rounded">
            <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium">
              {mounted ? (user?.name?.[0] || 'U') : 'U'}
            </div>
            <div className="hidden md:block text-left">
              <div className="text-sm font-medium leading-tight">{mounted ? user?.name : undefined}</div>
              <div className="text-xs text-muted-foreground">
                {mounted
                  ? user?.current_business_id
                    ? user?.businesses?.find((b) => b.id === user.current_business_id)?.role
                    : user?.businesses?.[0]?.role || 'viewer'
                  : undefined}
              </div>
            </div>
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          </button>
          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-2 w-48 bg-card border border-border rounded-lg shadow-lg py-1">
              <Link href="/settings" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-secondary">
                <User className="w-4 h-4" /> 商户设置
              </Link>
              <button onClick={logout} className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-secondary w-full text-destructive">
                <LogOut className="w-4 h-4" /> 退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
