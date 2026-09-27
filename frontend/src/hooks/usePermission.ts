import { useAuthStore } from '@/store/authStore';
import type { UserRole } from '@/types';

// 角色层级（数值越大权限越高）
const ROLE_LEVEL: Record<UserRole, number> = {
  super_admin: 100,
  owner: 90,
  manager: 70,
  employee: 50,
  viewer: 30,
  agent: 10,
};

// 角色默认权限映射
const ROLE_PERMISSIONS: Record<UserRole, string[]> = {
  super_admin: ['*'],
  owner: [
    'dashboard:read', 'product:*', 'inventory:*', 'order:*', 'customer:*',
    'agent:*', 'work_order:*', 'alert:*', 'memory:*', 'business:update',
    'audit:read', 'circuit:*', 'loop:*', 'feedback:*',
  ],
  manager: [
    'dashboard:read', 'product:read', 'product:write', 'inventory:*', 'order:*',
    'customer:*', 'agent:read', 'work_order:read', 'work_order:write',
    'alert:*', 'memory:read', 'business:update', 'loop:read', 'feedback:read',
  ],
  employee: [
    'dashboard:read', 'product:read', 'inventory:read', 'inventory:write',
    'order:read', 'order:write', 'customer:read', 'customer:write',
    'agent:read', 'work_order:read', 'alert:read', 'alert:write', 'memory:read',
  ],
  viewer: [
    'dashboard:read', 'product:read', 'inventory:read', 'order:read',
    'customer:read', 'agent:read', 'work_order:read', 'alert:read',
    'memory:read', 'loop:read',
  ],
  agent: ['*'],
};

export function usePermission() {
  const user = useAuthStore((s) => s.user);
  // 角色按商户区分，从当前商户获取
  const role: UserRole = (() => {
    if (!user) return 'viewer';
    if (user.current_business_id) {
      const biz = user.businesses?.find((b) => b.id === user.current_business_id);
      if (biz?.role) return biz.role;
    }
    return user.businesses?.[0]?.role || 'viewer';
  })();

  const hasPermission = (permission: string): boolean => {
    if (!user) return false;
    const perms = ROLE_PERMISSIONS[role] || [];
    if (perms.includes('*')) return true;
    // 支持通配符，如 product:* 匹配 product:read
    if (perms.includes(permission)) return true;
    const module = permission.split(':')[0];
    return perms.includes(`${module}:*`);
  };

  const hasRole = (requiredRole: UserRole): boolean => {
    return ROLE_LEVEL[role] >= ROLE_LEVEL[requiredRole];
  };

  return { hasPermission, hasRole, role };
}
