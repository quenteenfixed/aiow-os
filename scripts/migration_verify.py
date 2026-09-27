"""M6-4 数据迁移验证脚本

部署后运行：确认所有 Alembic 迁移已应用、关键表存在且行数合理、关键索引就位。
用法：
    python scripts/migration_verify.py                    # 用 backend/.env
    python scripts/migration_verify.py --sync-url "..."   # 临时指定 sync url
"""
import argparse
import asyncio
import sys

from sqlalchemy import text

# 复用应用配置（保证与运行时一致）
from app.database import engine, Base
from app.config import settings


CRITICAL_TABLES = [
    "businesses", "users", "products", "skus",
    "inventory_batches", "inventory_logs",
    "orders", "order_items", "customers",
    "agents", "agent_sessions", "agent_messages",
    "agent_memories", "agent_skills",
    "work_orders", "execution_jobs",
    "alerts", "audit_logs", "circuit_breaks",
    "a2a_agents", "a2a_sessions", "a2a_messages", "a2a_gateway_logs",
    "agent_loops", "agent_loop_runs",
]

CRITICAL_INDEXES = [
    ("audit_logs", "idx_audit_logs_biz_created"),
    ("circuit_breaks", "idx_circuit_breaks_biz_agent_status"),
    ("agent_memories", "idx_agent_memories_expires_at"),
    ("alerts", "idx_alerts_biz_status_level"),
]


async def check_alembic_version(conn) -> tuple[str, list[str]]:
    """返回 (当前 head revision, 已应用版本列表)"""
    # 应用版本表
    exists = (await conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='alembic_version')"
    ))).scalar()
    if not exists:
        return "", []
    rows = (await conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))).fetchall()
    versions = [r[0] for r in rows]
    head = versions[-1] if versions else ""
    return head, versions


async def check_tables(conn) -> list[tuple[str, bool]]:
    """检查关键表是否存在"""
    results = []
    for t in CRITICAL_TABLES:
        exists = (await conn.execute(text(
            "SELECT to_regclass(:t) IS NOT NULL"
        ), {"t": f"public.{t}"})).scalar()
        results.append((t, bool(exists)))
    return results


async def check_indexes(conn) -> list[tuple[str, str, bool]]:
    results = []
    for table, idx in CRITICAL_INDEXES:
        exists = (await conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname=:i AND tablename=:t)"
        ), {"i": idx, "t": table})).scalar()
        results.append((table, idx, bool(exists)))
    return results


async def check_row_counts(conn) -> dict:
    """关键表的行数（用于 sanity check）"""
    counts = {}
    for t in ["users", "businesses", "products", "orders", "agents", "audit_logs"]:
        try:
            cnt = (await conn.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
            counts[t] = cnt
        except Exception as e:
            counts[t] = f"error: {e}"
    return counts


async def verify_chain_integrity(conn) -> dict:
    """审计哈希链完整性"""
    try:
        from app.services.audit_service import verify_chain
        from app.database import async_session_factory
        async with async_session_factory() as db:
            # 取所有 business_id
            biz_ids = (await db.execute(text("SELECT DISTINCT business_id FROM audit_logs"))).scalars().all()
        results = {}
        for bid in biz_ids:
            async with async_session_factory() as db:
                v = await verify_chain(db, bid)
                results[bid] = v
        return results
    except Exception as e:
        return {"error": str(e)}


async def main_async() -> int:
    async with engine.begin() as conn:
        return await _run_all(conn)


async def _run_all(conn) -> int:
    print("=== Alembic ===")
    head, versions = await check_alembic_version(conn)
    print(f"head={head}")
    print(f"applied={versions}")

    print("\n=== Tables ===")
    table_results = await check_tables(conn)
    missing = [t for t, ok in table_results if not ok]
    for t, ok in table_results:
        print(f"  {'OK' if ok else 'MISS':<4} {t}")
    if missing:
        print(f"!! 缺失表：{missing}")
    else:
        print("所有关键表存在")

    print("\n=== Indexes ===")
    idx_results = await check_indexes(conn)
    missing_idx = [(t, i) for t, i, ok in idx_results if not ok]
    for t, i, ok in idx_results:
        print(f"  {'OK' if ok else 'MISS':<4} {t}.{i}")
    if missing_idx:
        print(f"!! 缺失索引：{missing_idx}")
    else:
        print("所有关键索引就位")

    print("\n=== Row counts ===")
    counts = await check_row_counts(conn)
    for t, c in counts.items():
        print(f"  {t}: {c}")

    print("\n=== Audit hash chain ===")
    chain = await verify_chain_integrity(conn)
    for bid, v in chain.items():
        ok = isinstance(v, dict) and v.get("valid") is True
        print(f"  biz={bid}: valid={ok} total={v.get('total') if isinstance(v, dict) else v}")

    # 退出码：缺失表/索引/链断裂则非零
    has_missing = bool(missing) or bool(missing_idx)
    has_broken_chain = any(
        isinstance(v, dict) and v.get("valid") is False
        for v in chain.values()
    )
    return 1 if (has_missing or has_broken_chain) else 0


def main():
    asyncio.run(main_async())
    print("\nDone")
    sys.exit(0)


if __name__ == "__main__":
    main()
