'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Plug, Key, FileText, Activity } from 'lucide-react';

interface Capability {
  name: string;
  path: string;
  method: string;
  description: string;
  parameters: Record<string, unknown>;
}

export default function A2APage() {
  const [tab, setTab] = useState('capabilities');
  const [capabilities, setCapabilities] = useState<Capability[]>([]);

  useEffect(() => {
    api.get<any>('/a2a/capabilities')
      .then((res) => {
        // A2A 响应为 Fencing 格式：{ data: [...], fencing: {...} }
        const list = Array.isArray(res) ? res : res?.data || [];
        setCapabilities(list);
      })
      .catch(() => setCapabilities([]));
  }, []);

  const tabs = [
    { key: 'capabilities', label: '能力文档', icon: FileText },
    { key: 'keys', label: 'API Key', icon: Key },
    { key: 'logs', label: '调用日志', icon: Activity },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">A2A 网关</h1>

      <div className="flex gap-2 border-b border-border">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1 px-4 py-2 text-sm border-b-2 -mb-px ${tab === t.key ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'}`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'capabilities' && (
        <div className="space-y-3">
          {capabilities.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">暂无对外能力</div>
          ) : (
            capabilities.map((cap, i) => (
              <div key={i} className="bg-card border border-border rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-xs px-2 py-0.5 rounded font-mono ${cap.method === 'GET' ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'}`}>{cap.method}</span>
                  <code className="text-sm font-mono">{cap.path}</code>
                </div>
                <div className="text-sm font-medium">{cap.name}</div>
                <div className="text-sm text-muted-foreground mt-1">{cap.description}</div>
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer text-primary">参数详情</summary>
                  <pre className="bg-muted p-3 rounded mt-2 overflow-x-auto">{JSON.stringify(cap.parameters, null, 2)}</pre>
                </details>
              </div>
            ))
          )}
        </div>
      )}

      {tab === 'keys' && (
        <div className="bg-card border border-border rounded-lg p-6 text-center text-muted-foreground">
          <Key className="w-12 h-12 mx-auto mb-3" />
          <p>API Key 管理功能</p>
          <p className="text-sm mt-1">创建、吊销、轮换 API Key</p>
        </div>
      )}

      {tab === 'logs' && (
        <div className="bg-card border border-border rounded-lg p-6 text-center text-muted-foreground">
          <Activity className="w-12 h-12 mx-auto mb-3" />
          <p>A2A 调用日志</p>
          <p className="text-sm mt-1">查看外部 Agent 调用记录</p>
        </div>
      )}
    </div>
  );
}
