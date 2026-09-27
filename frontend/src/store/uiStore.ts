import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// 全局 UI 状态
interface UIState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
    }),
    { name: 'aiow-ui' },
  ),
);

// 熔断状态（全站共享）
interface CircuitState {
  isTriggered: boolean;
  reason: string | null;
  triggeredAt: string | null;
  setTriggered: (reason: string, triggeredAt: string) => void;
  setNormal: () => void;
}

export const useCircuitStore = create<CircuitState>((set) => ({
  isTriggered: false,
  reason: null,
  triggeredAt: null,
  setTriggered: (reason, triggeredAt) => set({ isTriggered: true, reason, triggeredAt }),
  setNormal: () => set({ isTriggered: false, reason: null, triggeredAt: null }),
}));

// 通知状态
export interface NotificationItem {
  id: string;
  type: 'alert' | 'work_order' | 'order' | 'circuit' | 'system';
  title: string;
  message: string;
  link?: string;
  createdAt: string;
  read: boolean;
}

interface NotificationState {
  items: NotificationItem[];
  unreadCount: number;
  addNotification: (item: Omit<NotificationItem, 'id' | 'createdAt' | 'read'>) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
}

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set) => ({
      items: [],
      unreadCount: 0,
      addNotification: (item) =>
        set((s) => {
          const newItem: NotificationItem = {
            ...item,
            id: Date.now().toString(),
            createdAt: new Date().toISOString(),
            read: false,
          };
          return { items: [newItem, ...s.items].slice(0, 50), unreadCount: s.unreadCount + 1 };
        }),
      markAsRead: (id) =>
        set((s) => ({
          items: s.items.map((i) => (i.id === id ? { ...i, read: true } : i)),
          unreadCount: Math.max(0, s.unreadCount - 1),
        })),
      markAllAsRead: () =>
        set((s) => ({
          items: s.items.map((i) => ({ ...i, read: true })),
          unreadCount: 0,
        })),
    }),
    { name: 'aiow-notifications' },
  ),
);
