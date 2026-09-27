import type { ApiResponse } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

// 获取 Token
function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  const token = localStorage.getItem('access_token');
  if (token) return token;
  // 后备：从 cookie 读取（中间件鉴权使用 cookie）
  const match = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('refresh_token');
}

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

// 刷新 Token
async function refreshToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    const data = await res.json();
    if (data.code === 0 && data.data) {
      localStorage.setItem('access_token', data.data.access_token);
      localStorage.setItem('refresh_token', data.data.refresh_token);
      return data.data.access_token;
    }
  } catch {
    // ignore
  }
  return null;
}

// 统一请求方法
export async function request<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let token = getAccessToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  // 401 尝试刷新 Token
  if (res.status === 401) {
    const newToken = await refreshToken();
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`;
      res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
    }
  }

  let json: any;
  try {
    json = await res.json();
  } catch {
    throw new Error('响应解析失败');
  }

  // 兼容无 code 字段的响应（如 A2A Fencing 响应）
  if (typeof json.code === 'undefined') {
    return json as T;
  }

  if (json.code === 0) {
    return json.data as T;
  }

  // 特殊错误码处理
  if (json.code === 40101) {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    throw new Error(json.message || '未登录');
  }

  if (json.code === 40301) {
    throw new Error('权限不足');
  }

  throw new Error(json.message || '请求失败');
}

// 便捷方法
export const api = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

// SSE 流式请求（用于 Agent 聊天）
export function streamRequest(
  path: string,
  body: unknown,
  callbacks: {
    onText: (text: string) => void;
    onToolCall: (data: string) => void;
    onToolResult: (data: string) => void;
    onDone: () => void;
    onError: (err: Error) => void;
  },
): () => void {
  const token = getAccessToken();
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        callbacks.onError(new Error(`请求失败: ${res.status}`));
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            switch (event.event) {
              case 'text':
                callbacks.onText(event.data);
                break;
              case 'tool_call':
                callbacks.onToolCall(event.data);
                break;
              case 'tool_result':
                callbacks.onToolResult(event.data);
                break;
              case 'done':
                callbacks.onDone();
                break;
              case 'error':
                callbacks.onError(new Error(event.data || '流式响应错误'));
                break;
            }
          } catch {
            // 忽略非 JSON 行
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError(err as Error);
      }
    }
  })();

  return () => controller.abort();
}
