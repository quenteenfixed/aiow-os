'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import { ArrowLeft, ChevronDown, ChevronRight } from 'lucide-react';

interface LoopRun {
  id: number;
  loop_id: number;
  status: 'success' | 'partial' | 'failed';
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
  anomaly_count: number;
  work_order_count: number;
  memory_count: number;
  stages: Stage[];
}

interface Stage {
  name: string;
  label: string;
  icon: string;
  status: 'success' | 'partial' | 'failed' | 'skipped';
  content: string;
  data?: Record<string, unknown>;
}

const STAGE_META = [
  { name: 'observe', label: '感知 Observe', icon: '👁️' },
  { name: 'detect', label: '检测 Detect', icon: '🔍' },
  { name: 'analyze', label: '分析 Analyze', icon: '🧠' },
  { name: 'plan', label: '方案 Plan', icon: '📋' },
  { name: 'execute', label: '执行 Execute', icon: '⚙️' },
  { name: 'evaluate', label: '评估 Evaluate', icon: '📊' },
  { name: 'learn', label: '学习 Learn', icon: '📚' },
];

const STATUS_COLORS: Record<string, string> = {
  success: 'border-success',
  partial: 'border-warning',
  failed: 'border-destructive',
  skipped: 'border-gray-300',
};
const STATUS_DOT: Record<string, string> = {
  success: 'bg-success', partial: 'bg-warning', failed: 'bg-destructive', skipped: 'bg-gray-300',
};

export default function LoopRunDetailPage() {
  const params = useParams();
  const runId = Number(params.runId);
  const [run, setRun] = useState<LoopRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set(['execute', 'evaluate']));

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<LoopRun>(`/loops/runs/${runId}`);
        setRun(data);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [runId]);

  const toggleStage = (name: string) => {
    setExpandedStages((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  if (loading) return <div className="text-center py-20 text-muted-foreground">加载中...</div>;
  if (!run) return <div className="text-center py-20 text-muted-foreground">运行记录不存在</div>;

  return (
    <div className="space-y-4">
      <a href={`/loops/${run.loop_id}`} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> 返回循环详情
      </a>

      {/* 运行总览 */}
      <div className="bg-card border border-border rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">循环运行详情 #{run.id}</h1>
          <span className={`text-xs px-2 py-1 rounded ${run.status === 'success' ? 'bg-success/10 text-success' : run.status === 'failed' ? 'bg-destructive/10 text-destructive' : 'bg-warning/10 text-warning'}`}>
            {run.status}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <Stat label="开始时间" value={formatDate(run.started_at)} />
          <Stat label="耗时" value={`${run.duration_ms}ms`} />
          <Stat label="异常数" value={String(run.anomaly_count)} />
          <Stat label="工单数" value={String(run.work_order_count)} />
          <Stat label="记忆数" value={String(run.memory_count)} />
        </div>
      </div>

      {/* 七阶段时间轴 */}
      <div className="bg-card border border-border rounded-lg p-5">
        <h2 className="font-semibold mb-4">OUPDEL 七阶段执行过程</h2>
        <div className="space-y-2">
          {STAGE_META.map((meta, idx) => {
            const stage = run.stages?.find((s) => s.name === meta.name);
            const isExpanded = expandedStages.has(meta.name);
            return (
              <div key={meta.name} className={`border-l-2 ${stage ? STATUS_COLORS[stage.status] : 'border-gray-200'} pl-4 py-2`}>
                <button onClick={() => toggleStage(meta.name)} className="flex items-center gap-3 w-full text-left">
                  <span className="text-lg">{meta.icon}</span>
                  <span className="font-medium text-sm">
                    {idx + 1}. {meta.label}
                  </span>
                  {stage && (
                    <span className={`w-2 h-2 rounded-full ${STATUS_DOT[stage.status]}`} />
                  )}
                  <span className="ml-auto text-muted-foreground">
                    {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </span>
                </button>
                {isExpanded && stage && (
                  <div className="mt-3 ml-7 text-sm">
                    <p className="text-muted-foreground mb-2">{stage.content}</p>
                    {stage.data && (
                      <pre className="bg-muted p-3 rounded text-xs overflow-x-auto">{JSON.stringify(stage.data, null, 2)}</pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}
