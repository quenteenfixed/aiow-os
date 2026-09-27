'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { AuditLog } from '@/types';
import { Search, ShieldCheck } from 'lucide-react';

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ valid: boolean; message: string } | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await api.get<{ items: AuditLog[] }>(`/audit/logs?page=1&page_size=50`);
        setLogs(data.items);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const data = await api.post<{ valid: boolean }>('/audit/verify');
      setVerifyResult({ valid: data.valid, message: data.valid ? '所有审计日志哈希链连续，无篡改' : '检测到哈希链断裂' });
    } catch (err) {
      setVerifyResult({ valid: false, message: (err as Error).message });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">审计日志</h1>
        <button onClick={handleVerify} disabled={verifying} className="flex items-center gap-1 px-3 py-2 rounded-md border border-border text-sm hover:bg-secondary disabled:opacity-50">
          <ShieldCheck className="w-4 h-4" /> {verifying ? '校验中...' : '哈希链校验'}
        </button>
      </div>

      {verifyResult && (
        <div className={`p-4 rounded-lg ${verifyResult.valid ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
          {verifyResult.message}
        </div>
      )}

      <div className="relative max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="搜索操作..."
          className="w-full pl-9 pr-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-3 font-medium">时间</th>
              <th className="text-left px-4 py-3 font-medium">操作人</th>
              <th className="text-left px-4 py-3 font-medium">操作</th>
              <th className="text-left px-4 py-3 font-medium">资源</th>
              <th className="text-left px-4 py-3 font-medium">IP</th>
              <th className="text-left px-4 py-3 font-medium">结果</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center py-12 text-muted-foreground">加载中...</td></tr>
            ) : logs.length === 0 ? (
              <tr><td colSpan={6} className="text-center py-12 text-muted-foreground">暂无审计日志</td></tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="border-t border-border hover:bg-secondary/50">
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(log.created_at, 'MM-dd HH:mm:ss')}</td>
                  <td className="px-4 py-3">{log.operator_name}</td>
                  <td className="px-4 py-3">{log.action}</td>
                  <td className="px-4 py-3 text-muted-foreground">{log.resource_type}{log.resource_id ? `#${log.resource_id}` : ''}</td>
                  <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{log.ip || '-'}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${log.result === 'success' ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                      {log.result}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
