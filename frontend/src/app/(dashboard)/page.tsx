'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { formatMoney, formatDate } from '@/lib/format';
import type { DashboardOverview, SalesTrendPoint, InventoryTrendPoint, AgentActivity, EfficiencyComparison, WorkOrder, Alert } from '@/types';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { TrendingUp, TrendingDown, Package, ShoppingCart, Bot, AlertTriangle } from 'lucide-react';

const PIE_COLORS = ['#2563eb', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6'];

export default function DashboardPage() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [salesTrend, setSalesTrend] = useState<SalesTrendPoint[]>([]);
  const [invTrend, setInvTrend] = useState<InventoryTrendPoint[]>([]);
  const [activity, setActivity] = useState<AgentActivity | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyComparison | null>(null);
  const [pendingOrders, setPendingOrders] = useState<WorkOrder[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [ov, st, it, ac, ef, wo, al] = await Promise.all([
          api.get<DashboardOverview>('/dashboard/overview?days=7'),
          api.get<SalesTrendPoint[]>('/dashboard/sales-trend?days=30'),
          api.get<InventoryTrendPoint[]>('/dashboard/inventory-trend?days=30'),
          api.get<AgentActivity>('/dashboard/agent-activity?days=7'),
          api.get<EfficiencyComparison>('/dashboard/efficiency?days=30'),
          api.get<{ items: WorkOrder[] }>('/work-orders?status=pending&page_size=5'),
          api.get<{ items: Alert[] }>('/alerts?status=active&page_size=5'),
        ]);
        setOverview(ov);
        setSalesTrend(st);
        setInvTrend(it);
        setActivity(ac);
        setEfficiency(ef);
        setPendingOrders(wo.items || []);
        setAlerts(al.items || []);
      } catch (err) {
        console.error('加载仪表盘数据失败', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  }

  const agentPieData = overview
    ? Object.entries(overview.agents.by_autonomy_level || {}).map(([level, count]) => ({ name: level, value: count }))
    : [];

  return (
    <div className="space-y-6">
      {/* 6 个核心指标卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard label="销售额" value={formatMoney(overview?.sales.total_amount ?? 0)} icon={<TrendingUp className="w-4 h-4" />} />
        <MetricCard label="毛利率" value="--" hint="基于成本计算" icon={<TrendingUp className="w-4 h-4" />} />
        <MetricCard label="订单数" value={String(overview?.sales.order_count ?? 0)} icon={<ShoppingCart className="w-4 h-4" />} />
        <MetricCard label="客单价" value={formatMoney(overview?.sales.avg_order_value ?? 0)} icon={<Package className="w-4 h-4" />} />
        <MetricCard label="活跃Agent" value={String(overview?.agents.total ?? 0)} icon={<Bot className="w-4 h-4" />} />
        <MetricCard label="活跃告警" value={String(overview?.alerts.active ?? 0)} icon={<AlertTriangle className="w-4 h-4 text-warning" />} danger={(overview?.alerts.active ?? 0) > 0} />
      </div>

      {/* 销售趋势 + 效率对比 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="销售趋势（近30天）">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={salesTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Line type="monotone" dataKey="amount" stroke="#2563eb" strokeWidth={2} dot={false} name="销售额" />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Agent vs 人工效率">
          {efficiency ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={[
                { name: '工单数', Agent: efficiency.agent_created?.total ?? 0, 人工: efficiency.manual_created?.total ?? 0 },
                { name: '平均时长(分)', Agent: efficiency.agent_created?.avg_processing_minutes ?? 0, 人工: efficiency.manual_created?.avg_processing_minutes ?? 0 },
                { name: '通过率(%)', Agent: (efficiency.agent_created?.approval_rate ?? 0) * 100, 人工: (efficiency.manual_created?.approval_rate ?? 0) * 100 },
              ]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="name" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Legend />
                <Bar dataKey="Agent" fill="#2563eb" />
                <Bar dataKey="人工" fill="#94a3b8" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-muted-foreground">暂无数据</div>
          )}
        </Card>
      </div>

      {/* 库存趋势 + Agent分布 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="库存出入库趋势（近30天）">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={invTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip />
              <Legend />
              <Bar dataKey="in" fill="#22c55e" name="入库" />
              <Bar dataKey="out" fill="#ef4444" name="出库" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Agent 自主级别分布">
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={agentPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                {agentPieData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* 待审批工单 + 活跃告警 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="待审批工单" action={<a href="/work-orders" className="text-sm text-primary hover:underline">查看全部</a>}>
          {pendingOrders.length === 0 ? (
            <EmptyState text="暂无待审批工单" />
          ) : (
            <div className="space-y-2">
              {pendingOrders.map((wo) => (
                <a key={wo.id} href={`/work-orders/${wo.id}`} className="block p-3 rounded-md border border-border hover:bg-secondary transition-colors">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{wo.title}</span>
                    <RiskBadge level={wo.risk_level} />
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {wo.order_type} · {formatDate(wo.created_at, 'MM-dd HH:mm')}
                  </div>
                </a>
              ))}
            </div>
          )}
        </Card>

        <Card title="活跃告警" action={<a href="/alerts" className="text-sm text-primary hover:underline">查看全部</a>}>
          {alerts.length === 0 ? (
            <EmptyState text="暂无活跃告警" />
          ) : (
            <div className="space-y-2">
              {alerts.map((a) => (
                <a key={a.id} href={`/alerts/${a.id}`} className="block p-3 rounded-md border border-border hover:bg-secondary transition-colors">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{a.title}</span>
                    <LevelBadge level={a.level} />
                  </div>
                  <div className="text-xs text-muted-foreground mt-1 truncate">{a.content}</div>
                </a>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function MetricCard({ label, value, hint, icon, danger }: { label: string; value: string; hint?: string; icon: React.ReactNode; danger?: boolean }) {
  return (
    <div className={`bg-card border border-border rounded-lg p-4 ${danger ? 'border-warning' : ''}`}>
      <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
        {icon}
        {label}
      </div>
      <div className={`text-xl font-bold ${danger ? 'text-warning' : ''}`}>{value}</div>
      {hint && <div className="text-xs text-muted-foreground mt-1">{hint}</div>}
    </div>
  );
}

function Card({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="h-32 flex items-center justify-center text-muted-foreground text-sm">{text}</div>;
}

function RiskBadge({ level }: { level: string }) {
  const colors: Record<string, string> = { low: 'bg-success/10 text-success', medium: 'bg-warning/10 text-warning', high: 'bg-destructive/10 text-destructive' };
  return <span className={`text-xs px-2 py-0.5 rounded ${colors[level] || ''}`}>{level}</span>;
}

function LevelBadge({ level }: { level: string }) {
  const colors: Record<string, string> = { P0: 'bg-destructive text-white', P1: 'bg-orange-500 text-white', P2: 'bg-warning text-white', P3: 'bg-blue-500 text-white' };
  return <span className={`text-xs px-2 py-0.5 rounded font-medium ${colors[level] || ''}`}>{level}</span>;
}
