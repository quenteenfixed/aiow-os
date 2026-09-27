'use client';

import Sidebar from './Sidebar';
import Header from './Header';
import CircuitBreakerBar from './CircuitBreakerBar';
import { useUIStore } from '@/store/uiStore';
import { cn } from '@/lib/format';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { sidebarCollapsed } = useUIStore();

  return (
    <div className="min-h-screen bg-muted">
      <CircuitBreakerBar />
      <Sidebar />
      <div
        className={cn(
          'transition-all duration-200',
          sidebarCollapsed ? 'ml-16' : 'ml-60',
        )}
      >
        <Header />
        <main className="p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
