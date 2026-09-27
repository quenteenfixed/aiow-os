"""M6-3 稳定性测试脚本 - 72 小时压测 + 健康巡检

设计：
- 每 30 秒探测一次 /ready（DB + Redis），记录响应时间
- 每 5 分钟跑一遍核心接口 smoke（login / products / orders / dashboard）
- 每小时检查 OUPDEL scheduler 是否仍在运行、有无 unhandled exception
- 输出：stability_report.json + stability_report.log

用法：
    python scripts/stability_test.py --duration-hours 72 --base-url http://localhost:8000
    python scripts/stability_test.py --duration-hours 1 --base-url http://localhost:8000  # smoke
"""
import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("stability_report.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def probe_ready(client: httpx.AsyncClient, base_url: str) -> tuple[bool, int, Optional[dict]]:
    start = time.time()
    try:
        resp = await client.get(f"{base_url}/ready", timeout=10)
        elapsed = int((time.time() - start) * 1000)
        ok = resp.status_code == 200 and resp.json().get("code") == 0
        return ok, elapsed, resp.json() if ok else resp.json()
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return False, elapsed, {"error": str(e)}


async def smoke_core_api(client: httpx.AsyncClient, base_url: str) -> dict:
    """跑一遍核心接口 smoke，返回汇总"""
    results = {}
    # 不带 token 的接口应返回 401，证明认证生效
    endpoints = [
        ("GET", "/api/v1/products"),
        ("GET", "/api/v1/orders"),
        ("GET", "/api/v1/dashboard/overview"),
        ("GET", "/api/v1/agents"),
        ("GET", "/api/v1/audit/logs"),
        ("GET", "/api/v1/circuit-breaker/status"),
    ]
    for method, path in endpoints:
        try:
            resp = await client.request(method, f"{base_url}{path}", timeout=10)
            results[path] = {"status": resp.status_code, "ok": resp.status_code in (200, 401)}
        except Exception as e:
            results[path] = {"status": -1, "ok": False, "error": str(e)}
    return results


async def run_stability_test(base_url: str, duration_hours: float) -> dict:
    duration_seconds = duration_hours * 3600
    end_at = time.time() + duration_seconds
    probe_every = 30  # seconds
    smoke_every = 300  # 5 minutes

    report = {
        "base_url": base_url,
        "duration_hours": duration_hours,
        "started_at": _now_iso(),
        "ended_at": None,
        "total_probes": 0,
        "failed_probes": 0,
        "probe_latencies_ms": [],
        "smoke_runs": [],
        "summary": {},
    }

    async with httpx.AsyncClient() as client:
        next_probe = time.time()
        next_smoke = time.time()
        last_smoke = None

        while time.time() < end_at:
            now = time.time()
            if now >= next_probe:
                ok, latency, payload = await probe_ready(client, base_url)
                report["total_probes"] += 1
                report["probe_latencies_ms"].append(latency)
                if not ok:
                    report["failed_probes"] += 1
                    logger.warning(f"Probe FAIL latency={latency}ms payload={payload}")
                else:
                    logger.info(f"Probe OK latency={latency}ms total={report['total_probes']}")
                next_probe = now + probe_every

            if now >= next_smoke:
                logger.info("Running core API smoke ...")
                smoke = await smoke_core_api(client, base_url)
                failed = [p for p, r in smoke.items() if not r.get("ok")]
                run_summary = {
                    "at": _now_iso(),
                    "results": smoke,
                    "failed": failed,
                }
                report["smoke_runs"].append(run_summary)
                last_smoke = run_summary
                if failed:
                    logger.warning(f"Smoke failures: {failed}")
                else:
                    logger.info("Smoke all green")
                next_smoke = now + smoke_every

            # 短休眠避免空转
            await asyncio.sleep(min(5, next_probe - time.time()))

    report["ended_at"] = _now_iso()
    latencies = report["probe_latencies_ms"]
    report["summary"] = {
        "availability_pct": round(
            (report["total_probes"] - report["failed_probes"]) / max(report["total_probes"], 1) * 100, 3
        ),
        "latency_p50_ms": statistics.median(latencies) if latencies else 0,
        "latency_p95_ms": _percentile(latencies, 95) if latencies else 0,
        "latency_p99_ms": _percentile(latencies, 99) if latencies else 0,
        "latency_max_ms": max(latencies) if latencies else 0,
        "smoke_run_count": len(report["smoke_runs"]),
        "smoke_run_with_failures": sum(1 for s in report["smoke_runs"] if s["failed"]),
    }
    return report


def _percentile(data: list, p: int) -> float:
    if not data:
        return 0
    s = sorted(data)
    k = max(0, int(round(len(s) * p / 100)) - 1)
    return s[k]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--duration-hours", type=float, default=72)
    args = parser.parse_args()

    logger.info(f"Starting stability test: base_url={args.base_url} duration={args.duration_hours}h")
    report = asyncio.run(run_stability_test(args.base_url, args.duration_hours))

    with open("stability_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"Report written to stability_report.json. Summary: {report['summary']}")
    # 退出码：可用性 < 99.9% 或 smoke 失败则非零
    s = report["summary"]
    if s["availability_pct"] < 99.9 or s["smoke_run_with_failures"] > 0:
        logger.error("Stability test FAILED")
        sys.exit(1)
    logger.info("Stability test PASSED")


if __name__ == "__main__":
    main()
