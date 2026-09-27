'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { WorkOrder } from '@/types';
import { ArrowLeft } from 'lucide-react';

export default function WorkOrderDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [order, setOrder] = useState<WorkOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<WorkOrder>(`/work-orders/${id}`);
        setOrder(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const handleApprove = async () => {
    setSubmitting(true);
    try {
      await api.post(`/work-orders/${id}/approve`, { comment });
      location.reload();
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!comment) { alert('请填写拒绝原因'); return; }
    setSubmitting(true);
    try {
      await api.post(`/work-orders/${id}/reject`, { comment });
      location.reload();
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!order) return <div className="text-center py-20 text-muted-foreground">工单不存在</div>;

  return (
    <div className="space-y-4">
      <a href="/work-orders" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回工单列表
      </a>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">{order.title}</h1>
          <p className="text-sm text-muted-foreground mt-1">工单 #{order.id} · {formatDate(order.created_at)}</p>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-secondary">{order.status}</span>
      </div>

      {/* AI 决策依据区块 (P0) */}
      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <span className="text-lg">🤖</span> AI 决策依据
        </h2>
        <div className="space-y-4">
          <div className="border-l-2 border-primary pl-4">
            <div className="text-sm font-medium text-primary mb-1">感知数据</div>
            <p className="text-sm text-muted-foreground">{typeof order.metadata?.perceived_data === 'string' ? order.metadata.perceived_data : order.description || 'Agent 采集了相关经营数据用于决策分析。'}</p>
          </div>
          <div className="border-l-2 border-warning pl-4">
            <div className="text-sm font-medium text-warning mb-1">异常检测</div>
            <p className="text-sm text-muted-foreground">{typeof order.metadata?.anomaly === 'string' ? order.metadata.anomaly : order.reason || '检测到需要处理的经营异常。'}</p>
          </div>
          <div className="border-l-2 border-accent pl-4">
            <div className="text-sm font-medium text-accent mb-1">根因分析</div>
            <p className="text-sm text-muted-foreground">{typeof order.metadata?.analysis === 'string' ? order.metadata.analysis : 'Agent 对异常原因进行了分析。'}</p>
          </div>
          <div className="border-l-2 border-blue-500 pl-4">
            <div className="text-sm font-medium text-blue-500 mb-1">方案与风险评估</div>
            <p className="text-sm text-muted-foreground">{order.expected_result || 'Agent 生成了执行方案并评估了风险。'}</p>
          </div>
        </div>
      </div>

      {/* 基本信息 */}
      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4">工单信息</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div><span className="text-muted-foreground">类型：</span>{order.order_type}</div>
          <div><span className="text-muted-foreground">风险等级：</span>{order.risk_level}</div>
          <div><span className="text-muted-foreground">发起 Agent：</span>{order.agent_name || '-'}</div>
          <div><span className="text-muted-foreground">状态：</span>{order.status}</div>
        </div>
        <div className="mt-4 pt-4 border-t border-border">
          <div className="text-sm text-muted-foreground mb-1">详细描述</div>
          <p className="text-sm">{order.description}</p>
        </div>
        {order.params && (
          <div className="mt-4 pt-4 border-t border-border">
            <div className="text-sm text-muted-foreground mb-1">执行参数</div>
            <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">{JSON.stringify(order.params, null, 2)}</pre>
          </div>
        )}
      </div>

      {/* 审批链路时间线 */}
      {order.approval_history && order.approval_history.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">审批链路</h2>
          <div className="space-y-3">
            {order.approval_history.map((h, i) => (
              <div key={i} className="flex gap-3">
                <div className="w-2 h-2 rounded-full bg-primary mt-1.5" />
                <div>
                  <div className="text-sm">
                    <span className="font-medium">{h.operator_name}</span>
                    <span className="text-muted-foreground"> · {h.action}</span>
                  </div>
                  {h.comment && <div className="text-sm text-muted-foreground">{h.comment}</div>}
                  <div className="text-xs text-muted-foreground">{formatDate(h.created_at)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 审批操作 */}
      {order.status === 'pending' && (
        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="font-semibold mb-4">审批操作</h2>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="审批意见（拒绝时必填）..."
            className="w-full px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary mb-4"
            rows={3}
          />
          <div className="flex gap-2">
            <button onClick={handleApprove} disabled={submitting} className="px-4 py-2 rounded-md bg-success text-white hover:opacity-90 disabled:opacity-50">
              批准
            </button>
            <button onClick={handleReject} disabled={submitting} className="px-4 py-2 rounded-md bg-destructive text-destructive-foreground hover:opacity-90 disabled:opacity-50">
              拒绝
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
