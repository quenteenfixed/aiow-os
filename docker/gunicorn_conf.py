"""Gunicorn 生产配置

- preload_app=True：worker 启动前先加载应用，节省内存
- max_requests：worker 处理 1000 请求后重启，避免内存泄漏累积
- worker_connections：每个 worker 最大并发连接数
"""
import os
import multiprocessing

# 从环境变量读取
env = os.environ

bind = env.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(env.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(env.get("GUNICORN_TIMEOUT", 120))
graceful_timeout = int(env.get("GUNICORN_GRACEFUL_TIMEOUT", 30))
keepalive = int(env.get("GUNICORN_KEEPALIVE", 5))

# 性能与稳定性
preload_app = True  # 共享应用导入，节省内存
max_requests = 1000  # worker 处理 1000 请求后重启，规避泄漏
max_requests_jitter = 50  # 抖动，避免所有 worker 同时重启
worker_connections = 1000

# 日志
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = env.get("LOG_LEVEL", "info")

# 进程名（方便 ps 识别）
proc_name = "aiow-gunicorn"

# 平滑退出
capture_output = True
enable_stdio_inheritance = True


def when_ready(_):
    print(f"[Gunicorn] ready with {workers} workers", flush=True)


def on_exit(server):
    print("[Gunicorn] exiting", flush=True)
