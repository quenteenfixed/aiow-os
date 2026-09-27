"""M6-4 上线检查清单 - 自动化预检脚本

跑通后输出 EXIT 0 表示可以上线，否则输出非零并打印失败项。

用法：
    python scripts/launch_checklist.py --base-url http://localhost:8000 --env production
"""
import argparse
import asyncio
import sys

import httpx


CHECKS_PASSED = []
CHECKS_FAILED = []


def record(name: str, ok: bool, detail: str = ""):
    if ok:
        CHECKS_PASSED.append({"check": name, "detail": detail})
        print(f"[PASS] {name}: {detail}")
    else:
        CHECKS_FAILED.append({"check": name, "detail": detail})
        print(f"[FAIL] {name}: {detail}")


async def check_health(client, base_url):
    try:
        r = await client.get(f"{base_url}/health", timeout=5)
        record("Liveness /health", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        record("Liveness /health", False, str(e))


async def check_ready(client, base_url):
    try:
        r = await client.get(f"{base_url}/ready", timeout=5)
        body = r.json()
        ok = r.status_code == 200 and body.get("data", {}).get("ready") is True
        record("Readiness /ready (DB+Redis)", ok, f"body={body.get('data', {}).get('checks')}")
    except Exception as e:
        record("Readiness /ready", False, str(e))


async def check_docs_disabled(client, base_url, env):
    try:
        r = await client.get(f"{base_url}/docs", timeout=5, follow_redirects=False)
        if env == "production":
            record("Docs disabled in prod", r.status_code == 404, f"status={r.status_code}")
        else:
            record("Docs available in dev", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        record("Docs check", False, str(e))


async def check_auth_enforced(client, base_url):
    """未带 token 访问受保护资源应返回 401"""
    paths = ["/api/v1/products", "/api/v1/orders", "/api/v1/agents"]
    for p in paths:
        try:
            r = await client.get(f"{base_url}{p}", timeout=5)
            ok = r.status_code == 401
            record(f"Auth enforced {p}", ok, f"status={r.status_code}")
        except Exception as e:
            record(f"Auth enforced {p}", False, str(e))


async def check_metrics_endpoint(client, base_url):
    try:
        r = await client.get(f"{base_url}/metrics", timeout=5)
        record("Metrics endpoint", r.status_code == 200, f"status={r.status_code}")
    except Exception as e:
        record("Metrics endpoint", False, str(e))


async def check_circuit_breaker_status(client, base_url):
    try:
        r = await client.get(f"{base_url}/api/v1/circuit-breaker/status", timeout=5)
        # 未带 token 应该 401，证明该接口受保护
        record("Circuit breaker endpoint protected", r.status_code == 401, f"status={r.status_code}")
    except Exception as e:
        record("Circuit breaker endpoint", False, str(e))


async def main_async(base_url: str, env: str):
    async with httpx.AsyncClient() as client:
        await check_health(client, base_url)
        await check_ready(client, base_url)
        await check_docs_disabled(client, base_url, env)
        await check_auth_enforced(client, base_url)
        await check_metrics_endpoint(client, base_url)
        await check_circuit_breaker_status(client, base_url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--env", default="production")
    args = parser.parse_args()

    asyncio.run(main_async(args.base_url, args.env))

    print()
    print("=" * 60)
    print(f"Total: {len(CHECKS_PASSED) + len(CHECKS_FAILED)}  "
          f"PASS: {len(CHECKS_PASSED)}  FAIL: {len(CHECKS_FAILED)}")
    print("=" * 60)
    if CHECKS_FAILED:
        print("Failed checks:")
        for c in CHECKS_FAILED:
            print(f"  - {c['check']}: {c['detail']}")
        sys.exit(1)
    print("All pre-launch checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
