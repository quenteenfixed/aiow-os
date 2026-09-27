'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';
import { api, streamRequest } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { AgentSession, ChatMessage, ToolCall } from '@/types';
import { Send, StopCircle, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';

export default function AgentChatPage() {
  const params = useParams();
  const agentId = Number(params.id);
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const stopRef = useRef<(() => void) | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 加载会话列表
  useEffect(() => {
    api.get<{ items: AgentSession[] }>(`/agents/${agentId}/sessions?status=active&page=1&page_size=20`)
      .then((d: { items: AgentSession[] }) => {
        setSessions(d.items);
        if (d.items.length > 0) setCurrentSessionId(d.items[0].id);
      })
      .catch(() => {});
  }, [agentId]);

  // 加载消息
  useEffect(() => {
    if (!currentSessionId) return;
    api.get<{ items: ChatMessage[] }>(`/agents/sessions/${currentSessionId}/messages?page=1&page_size=50`)
      .then((d) => setMessages(d.items))
      .catch(() => setMessages([]));
  }, [currentSessionId]);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const toggleTool = (id: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: input, created_at: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);

    const assistantId = (Date.now() + 1).toString();
    setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content: '', tool_calls: [], created_at: new Date().toISOString() }]);

    let toolCallMap: Record<string, ToolCall> = {};

    stopRef.current = streamRequest(
      `/agents/${agentId}/chat/stream`,
      { message: input, session_id: currentSessionId },
      {
        onText: (text) => {
          setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, content: m.content + text } : m));
        },
        onToolCall: (data) => {
          try {
            const tc = JSON.parse(data) as ToolCall;
            toolCallMap[tc.id] = { ...tc, status: 'running' };
            setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, tool_calls: Object.values(toolCallMap) } : m));
          } catch {}
        },
        onToolResult: (data) => {
          try {
            const result = JSON.parse(data);
            if (toolCallMap[result.id]) {
              toolCallMap[result.id] = { ...toolCallMap[result.id], result: result.result, status: result.status, duration_ms: result.duration_ms };
              setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, tool_calls: Object.values(toolCallMap) } : m));
            }
          } catch {}
        },
        onDone: () => { setSending(false); stopRef.current = null; },
        onError: (err) => {
          setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, content: m.content + `\n\n❌ ${err.message}` } : m));
          setSending(false);
          stopRef.current = null;
        },
      },
    );
  };

  const handleStop = () => { stopRef.current?.(); setSending(false); };

  const copyText = (text: string) => { navigator.clipboard.writeText(text); };

  return (
    <div className="flex h-[calc(100vh-8rem)] bg-card border border-border rounded-lg overflow-hidden">
      {/* 会话列表 */}
      <div className="w-60 border-r border-border flex flex-col">
        <div className="p-3 border-b border-border">
          <button
            onClick={async () => {
              try {
                const s = await api.post<AgentSession>(`/agents/${agentId}/sessions`, { title: '新会话' });
                setSessions((prev) => [s, ...prev]);
                setCurrentSessionId(s.id);
              } catch {}
            }}
            className="w-full py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:opacity-90"
          >
            + 新建会话
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setCurrentSessionId(s.id)}
              className={`w-full text-left px-3 py-2 text-sm border-b border-border ${currentSessionId === s.id ? 'bg-secondary' : 'hover:bg-secondary/50'}`}
            >
              <div className="truncate">{s.title}</div>
              <div className="text-xs text-muted-foreground">{formatDate(s.updated_at, 'MM-dd HH:mm')}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 消息区 */}
      <div className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((m) => (
            <div key={m.id} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
              <div className={`max-w-[80%] ${m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-secondary'} rounded-lg px-4 py-2`}>
                {m.role === 'assistant' && m.tool_calls && m.tool_calls.length > 0 && (
                  <div className="space-y-2 mb-2">
                    {m.tool_calls.map((tc) => (
                      <div key={tc.id} className="bg-card border border-border rounded text-xs">
                        <button onClick={() => toggleTool(tc.id)} className="w-full flex items-center gap-2 px-3 py-2 text-left">
                          {expandedTools.has(tc.id) ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          <span className="font-mono">{tc.tool_name}</span>
                          <span className={`ml-auto px-1.5 py-0.5 rounded text-[10px] ${tc.status === 'success' ? 'bg-success/10 text-success' : tc.status === 'error' ? 'bg-destructive/10 text-destructive' : 'bg-warning/10 text-warning'}`}>
                            {tc.status}
                          </span>
                        </button>
                        {expandedTools.has(tc.id) && (
                          <div className="border-t border-border p-3 space-y-2">
                            <div>
                              <div className="flex items-center justify-between text-muted-foreground mb-1">
                                <span>参数</span>
                                <button onClick={() => copyText(JSON.stringify(tc.arguments))} className="hover:text-primary"><Copy className="w-3 h-3" /></button>
                              </div>
                              <pre className="bg-muted p-2 rounded overflow-x-auto text-[11px]">{JSON.stringify(tc.arguments, null, 2)}</pre>
                            </div>
                            {tc.result !== undefined && (
                              <div>
                                <div className="flex items-center justify-between text-muted-foreground mb-1">
                                  <span>结果 {tc.duration_ms ? `(${tc.duration_ms}ms)` : ''}</span>
                                  <button onClick={() => copyText(JSON.stringify(tc.result))} className="hover:text-primary"><Copy className="w-3 h-3" /></button>
                                </div>
                                <pre className="bg-muted p-2 rounded overflow-x-auto text-[11px]">{JSON.stringify(tc.result, null, 2)}</pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <div className="text-sm whitespace-pre-wrap">{m.content}</div>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* 输入框 */}
        <div className="border-t border-border p-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
              className="flex-1 px-3 py-2 rounded-md border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary resize-none"
              rows={2}
            />
            {sending ? (
              <button onClick={handleStop} className="px-4 py-2 rounded-md bg-destructive text-destructive-foreground hover:opacity-90 flex items-center gap-1">
                <StopCircle className="w-4 h-4" /> 停止
              </button>
            ) : (
              <button onClick={handleSend} disabled={!input.trim()} className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50 flex items-center gap-1">
                <Send className="w-4 h-4" /> 发送
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
