"""M6-4 监控指标端点 - Prometheus exposition format

不引入 prometheus_client 重型依赖，自实现最小指标集（Counter/Gauge/Histogram 文本格式），
足够被 Prometheus server 抓取。后续需要更复杂指标时再切换到 prometheus_client。

指标：
- aiow_http_requests_total{method, path, status}
- aiow_http_request_duration_seconds_bucket{method, path, le}
- aiow_db_pool_used / aiow_db_pool_size
- aiow_redis_available
- aiow_oupdel_loop_runs_total{result}
- aiow_active_circuit_breakers{level}
"""
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["监控"])


class _MetricsRegistry:
    """极简指标注册表（线程安全）"""

    def __init__(self):
        self._lock = Lock()
        self._counters: dict[str, dict[str, float]] = {}  # name -> {labels_key -> value}
        self._gauges: dict[str, dict[str, float]] = {}
        self._histograms: dict[str, dict[str, list]] = {}  # name -> {labels_key -> [values]}
        self._hist_buckets: dict[str, list] = {}  # name -> [bucket_upper_bounds]
        self._labels_meta: dict[str, dict[str, dict]] = {}  # name -> {labels_key -> labels dict}

    def inc_counter(self, name: str, value: float = 1, **labels):
        key = self._labels_key(labels)
        with self._lock:
            series = self._counters.setdefault(name, {})
            series[key] = series.get(key, 0) + value
            meta = self._labels_meta.setdefault(name, {})
            meta.setdefault(key, labels)

    def set_gauge(self, name: str, value: float, **labels):
        key = self._labels_key(labels)
        with self._lock:
            series = self._gauges.setdefault(name, {})
            series[key] = value
            meta = self._labels_meta.setdefault(name, {})
            meta.setdefault(key, labels)

    def observe_histogram(self, name: str, value: float, buckets: list, **labels):
        key = self._labels_key(labels)
        with self._lock:
            series = self._histograms.setdefault(name, {})
            series.setdefault(key, []).append(value)
            self._hist_buckets[name] = buckets
            meta = self._labels_meta.setdefault(name, {})
            meta.setdefault(key, labels)

    @staticmethod
    def _labels_key(labels: dict) -> str:
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def render(self) -> str:
        """渲染为 Prometheus text exposition 格式"""
        lines = []
        with self._lock:
            for name, series in self._counters.items():
                lines.append(f"# TYPE {name} counter")
                for key, val in series.items():
                    labels = self._labels_meta.get(name, {}).get(key, {})
                    label_str = self._render_labels(labels)
                    lines.append(f"{name}{label_str} {val}")
            for name, series in self._gauges.items():
                lines.append(f"# TYPE {name} gauge")
                for key, val in series.items():
                    labels = self._labels_meta.get(name, {}).get(key, {})
                    label_str = self._render_labels(labels)
                    lines.append(f"{name}{label_str} {val}")
            for name, series in self._histograms.items():
                lines.append(f"# TYPE {name} histogram")
                buckets = self._hist_buckets.get(name, [])
                for key, values in series.items():
                    labels = self._labels_meta.get(name, {}).get(key, {})
                    # bucket
                    for b in buckets:
                        cnt = sum(1 for v in values if v <= b)
                        lbl = {**labels, "le": str(b)}
                        lines.append(f"{name}_bucket{self._render_labels(lbl)} {cnt}")
                    # +Inf
                    lbl = {**labels, "le": "+Inf"}
                    lines.append(f"{name}_bucket{self._render_labels(lbl)} {len(values)}")
                    # sum
                    lines.append(f"{name}_sum{self._render_labels(labels)} {sum(values)}")
                    # count
                    lines.append(f"{name}_count{self._render_labels(labels)} {len(values)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_labels(labels: dict) -> str:
        if not labels:
            return ""
        parts = []
        for k, v in sorted(labels.items()):
            # 转义
            v = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            parts.append(f'{k}="{v}"')
        return "{" + ",".join(parts) + "}"


registry = _MetricsRegistry()


# HTTP 请求指标收集中间件（在 main.py 的 SlowRequestMiddleware 之外，独立计数）
async def metrics_middleware(request: Request, call_next):
    """记录每个 HTTP 请求的计数与延迟（不区分 path 参数化，便于聚合）"""
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    method = request.method
    path = request.url.path
    status = response.status_code

    registry.inc_counter(
        "aiow_http_requests_total",
        method=method, path=path, status=str(status),
    )
    # 延迟直方图（秒）
    registry.observe_histogram(
        "aiow_http_request_duration_seconds",
        value=elapsed,
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        method=method, path=path,
    )
    return response


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus 抓取端点"""
    # 附加运行时 Gauge
    from app.database import engine
    from app.redis_client import RedisClient

    # DB pool
    try:
        pool = engine.pool
        registry.set_gauge("aiow_db_pool_size", pool.size())
        registry.set_gauge("aiow_db_pool_used", pool.checkedin() + pool.checkedout())
    except Exception:
        pass

    # Redis 可用性
    try:
        redis_ok = await RedisClient.health_check()
        registry.set_gauge("aiow_redis_available", 1 if redis_ok else 0)
    except Exception:
        registry.set_gauge("aiow_redis_available", 0)

    body = registry.render()
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
