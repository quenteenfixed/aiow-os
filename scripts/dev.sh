#!/usr/bin/env bash
# ============================================================
# AIOW 一键启停脚本
# 用法: ./scripts/dev.sh {start|stop|restart|status|logs}
# ============================================================
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

# 端口配置
BACKEND_PORT=8000
FRONTEND_PORT=3000
POSTGRES_PORT=5432
REDIS_PORT=6379

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[AIOW]${NC} $1"; }
warn() { echo -e "${YELLOW}[AIOW]${NC} $1"; }
err()  { echo -e "${RED}[AIOW]${NC} $1"; }

# ---------- 工具函数 ----------
port_in_use() { lsof -i :"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

stop_pid() {
  local pid=$1
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
}

stop_port() {
  local port=$1
  local pid
  pid=$(lsof -i :"$port" -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$pid" ]; then
    log "停止端口 $port 进程 (PID: $pid)"
    kill "$pid" 2>/dev/null || true
    sleep 1
    # 强杀
    lsof -i :"$port" -sTCP:LISTEN -t 2>/dev/null | xargs kill -9 2>/dev/null || true
  fi
}

# ---------- 基础设施 (PostgreSQL + Redis) ----------
# 检测 Postgres.app 安装路径
find_postgres_app() {
  # 优先使用最新版本
  local latest
  latest=$(ls -d /Applications/Postgres.app/Contents/Versions/* 2>/dev/null | sort -V | tail -1)
  if [ -n "$latest" ]; then
    echo "$latest"
    return 0
  fi
  return 1
}

# 检测 redis-server 可执行文件
find_redis_server() {
  for p in redis-server /opt/homebrew/opt/redis/bin/redis-server /usr/local/opt/redis/bin/redis-server; do
    if command -v "$p" >/dev/null 2>&1; then
      echo "$(command -v "$p")"
      return 0
    fi
  done
  return 1
}

start_infra() {
  # ---- PostgreSQL ----
  if port_in_use $POSTGRES_PORT; then
    log "PostgreSQL 已在运行 (端口 $POSTGRES_PORT)"
  else
    log "启动 PostgreSQL..."
    local pg_ver
    pg_ver=$(find_postgres_app) || true
    if [ -n "$pg_ver" ]; then
      local pg_ctl="$pg_ver/bin/pg_ctl"
      local pg_data="$HOME/Library/Application Support/Postgres/var-${pg_ver##*/}"
      if [ -f "$pg_ctl" ] && [ -d "$pg_data" ]; then
        "$pg_ctl" -D "$pg_data" -l "$LOG_DIR/postgres.log" start >/dev/null 2>&1 || {
          err "PostgreSQL 启动失败，请查看 $LOG_DIR/postgres.log"
          return 1
        }
      else
        err "找到 Postgres.app 但 pg_ctl 或数据目录不存在"
        return 1
      fi
    elif command -v pg_ctl >/dev/null 2>&1; then
      pg_ctl start >/dev/null 2>&1 || {
        err "PostgreSQL 启动失败"
        return 1
      }
    else
      err "未找到 PostgreSQL (Postgres.app 或 pg_ctl)"
      err "请安装 Postgres.app: https://postgresapp.com  或  brew install postgresql@16"
      return 1
    fi
    # 等待 PostgreSQL 就绪
    for i in $(seq 1 20); do
      if port_in_use $POSTGRES_PORT; then
        log "PostgreSQL 就绪"
        break
      fi
      sleep 1
    done
    port_in_use $POSTGRES_PORT || { err "PostgreSQL 启动超时"; return 1; }
  fi

  # ---- Redis (可选，后端优雅降级) ----
  if port_in_use $REDIS_PORT; then
    log "Redis 已在运行 (端口 $REDIS_PORT)"
  else
    local redis_bin
    redis_bin=$(find_redis_server) || true
    if [ -n "$redis_bin" ]; then
      log "启动 Redis..."
      nohup "$redis_bin" --port $REDIS_PORT > "$LOG_DIR/redis.log" 2>&1 &
      echo $! > "$LOG_DIR/redis.pid"
      for i in $(seq 1 10); do
        port_in_use $REDIS_PORT && { log "Redis 就绪"; break; }
        sleep 1
      done
    else
      warn "未安装 Redis，跳过（后端会自动降级运行，限流与 token 黑名单功能不可用）"
      warn "如需安装: brew install redis && brew services start redis"
    fi
  fi
}

stop_infra() {
  log "停止基础设施..."
  # Redis（仅停止由本脚本启动的）
  if [ -f "$LOG_DIR/redis.pid" ]; then
    stop_pid "$(cat "$LOG_DIR/redis.pid")"
    rm -f "$LOG_DIR/redis.pid"
  fi
  stop_port $REDIS_PORT
  # PostgreSQL：由 Postgres.app 管理，不强制停止（避免影响用户其他数据）
  if port_in_use $POSTGRES_PORT; then
    warn "PostgreSQL 仍在运行（由 Postgres.app 管理，如需停止请手动退出 Postgres.app）"
  fi
}

# ---------- 后端 (FastAPI / uvicorn) ----------
start_backend() {
  if port_in_use $BACKEND_PORT; then
    log "后端已在运行 (端口 $BACKEND_PORT)"
    return 0
  fi
  log "启动后端服务 (端口 $BACKEND_PORT)..."
  cd "$BACKEND_DIR"
  PYTHON="$BACKEND_DIR/.venv/bin/python"
  if [ ! -f "$PYTHON" ]; then
    err "未找到后端虚拟环境: $BACKEND_DIR/.venv"
    err "请先执行: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    return 1
  fi
  nohup "$PYTHON" -m uvicorn app.main:app --reload --host 0.0.0.0 --port $BACKEND_PORT \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$LOG_DIR/backend.pid"
  # 等待后端就绪
  for i in $(seq 1 20); do
    if curl -s "http://localhost:$BACKEND_PORT/api/v1/auth/me" >/dev/null 2>&1; then
      log "后端服务就绪 (PID: $(cat $LOG_DIR/backend.pid))"
      return 0
    fi
    sleep 1
  done
  warn "后端启动超时，请查看 $LOG_DIR/backend.log"
}

stop_backend() {
  log "停止后端服务..."
  if [ -f "$LOG_DIR/backend.pid" ]; then
    stop_pid "$(cat "$LOG_DIR/backend.pid")"
    rm -f "$LOG_DIR/backend.pid"
  fi
  stop_port $BACKEND_PORT
}

# ---------- 前端 (Next.js) ----------
start_frontend() {
  if port_in_use $FRONTEND_PORT; then
    log "前端已在运行 (端口 $FRONTEND_PORT)"
    return 0
  fi
  log "启动前端服务 (端口 $FRONTEND_PORT)..."
  cd "$FRONTEND_DIR"
  if [ ! -d "node_modules" ]; then
    warn "未安装前端依赖，正在安装..."
    npm install
  fi
  nohup npm run dev -- --hostname 0.0.0.0 --port $FRONTEND_PORT \
    > "$LOG_DIR/frontend.log" 2>&1 &
  echo $! > "$LOG_DIR/frontend.pid"
  # 等待前端就绪
  for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$FRONTEND_PORT/" 2>/dev/null | grep -qE "307|200"; then
      log "前端服务就绪 (PID: $(cat $LOG_DIR/frontend.pid))"
      return 0
    fi
    sleep 2
  done
  warn "前端启动超时，请查看 $LOG_DIR/frontend.log"
}

stop_frontend() {
  log "停止前端服务..."
  if [ -f "$LOG_DIR/frontend.pid" ]; then
    # Next.js 可能有子进程，杀掉进程组
    local pid
    pid=$(cat "$LOG_DIR/frontend.pid")
    [ -n "$pid" ] && pkill -P "$pid" 2>/dev/null || true
    stop_pid "$pid"
    rm -f "$LOG_DIR/frontend.pid"
  fi
  stop_port $FRONTEND_PORT
}

# ---------- 状态检查 ----------
show_status() {
  echo ""
  echo "========== AIOW 服务状态 =========="
  printf "%-12s %-10s %s\n" "服务" "状态" "地址"
  echo "----------------------------------------"
  for svc in "PostgreSQL:$POSTGRES_PORT" "Redis:$REDIS_PORT" "Backend:$BACKEND_PORT" "Frontend:$FRONTEND_PORT"; do
    name="${svc%%:*}"; port="${svc##*:}"
    if port_in_use "$port"; then
      printf "%-12s ${GREEN}%-10s${NC} %s\n" "$name" "运行中" "http://localhost:$port"
    else
      printf "%-12s ${RED}%-10s${NC} %s\n" "$name" "已停止" "http://localhost:$port"
    fi
  done
  echo "========================================"
  echo ""
}

# ---------- 日志 ----------
show_logs() {
  local svc=${1:-all}
  case "$svc" in
    backend)  tail -f "$LOG_DIR/backend.log" ;;
    frontend) tail -f "$LOG_DIR/frontend.log" ;;
    all)
      echo "=== 后端日志 ===" && tail -20 "$LOG_DIR/backend.log" 2>/dev/null
      echo "" && echo "=== 前端日志 ===" && tail -20 "$LOG_DIR/frontend.log" 2>/dev/null
      ;;
    *) err "未知服务: $svc (可选: backend|frontend|all)" ;;
  esac
}

# ---------- 主入口 ----------
cmd=${1:-status}
case "$cmd" in
  start)
    start_infra
    start_backend
    start_frontend
    show_status
    log "全部服务启动完成！访问: http://localhost:$FRONTEND_PORT"
    ;;
  stop)
    stop_frontend
    stop_backend
    stop_infra
    show_status
    ;;
  restart)
    stop_frontend; stop_backend
    start_infra; start_backend; start_frontend
    show_status
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs "${2:-all}"
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status|logs [backend|frontend|all]}"
    exit 1
    ;;
esac
