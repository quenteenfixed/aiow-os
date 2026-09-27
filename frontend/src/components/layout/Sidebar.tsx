'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useUIStore } from '@/store/uiStore';
import { usePermission } from '@/hooks/usePermission';
import { cn } from '@/lib/format';
import {
  LayoutDashboard, Package, Boxes, ShoppingCart, Users,
  Bot, ClipboardList, Bell, Brain, Settings, Shield, Zap,
  Plug, RefreshCw, BarChart3,
} from 'lucide-react';

interface MenuItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  permission: string;
}

const MENU_ITEMS: MenuItem[] = [
  { label: '仪表盘', href: '/', icon: LayoutDashboard, permission: 'dashboard:read' },
  { label: '商品管理', href: '/products', icon: Package, permission: 'product:read' },
  { label: '库存管理', href: '/inventory', icon: Boxes, permission: 'inventory:read' },
  { label: '订单管理', href: '/orders', icon: ShoppingCart, permission: 'order:read' },
  { label: '客户管理', href: '/customers', icon: Users, permission: 'customer:read' },
  { label: 'Agent 管理', href: '/agents', icon: Bot, permission: 'agent:read' },
  { label: '工单审批', href: '/work-orders', icon: ClipboardList, permission: 'work_order:read' },
  { label: '告警中心', href: '/alerts', icon: Bell, permission: 'alert:read' },
  { label: '记忆管理', href: '/memories', icon: Brain, permission: 'memory:read' },
  { label: 'OUPDEL 循环', href: '/loops', icon: RefreshCw, permission: 'loop:read' },
  { label: '反馈学习', href: '/feedback', icon: BarChart3, permission: 'feedback:read' },
  { label: '商户设置', href: '/settings', icon: Settings, permission: 'business:update' },
  { label: '审计日志', href: '/audit', icon: Shield, permission: 'audit:read' },
  { label: '熔断管理', href: '/circuit-breaker', icon: Zap, permission: 'circuit:*' },
  { label: 'A2A 网关', href: '/a2a', icon: Plug, permission: 'business:*' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed } = useUIStore();
  const { hasPermission } = usePermission();
  const [mounted, setMounted] = useState(false);

  // 延迟到客户端挂载后再使用持久化状态，避免 SSR/CSR hydration 不一致
  useEffect(() => {
    setMounted(true);
  }, []);

  const collapsed = mounted ? sidebarCollapsed : false;
  const visibleItems = mounted
    ? MENU_ITEMS.filter((item) => hasPermission(item.permission))
    : [];

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 h-full bg-card border-r border-border transition-all duration-200 z-40',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      <div className="h-14 flex items-center justify-center border-b border-border">
        <Link href="/" className="flex items-center gap-2 font-bold text-primary">
          <span className="text-xl">🤖</span>
          {!collapsed && <span>AIOW</span>}
        </Link>
      </div>
      <nav className="p-2 space-y-1 overflow-y-auto h-[calc(100%-3.5rem)]">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
              )}
            >
              <Icon className="w-5 h-5 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
