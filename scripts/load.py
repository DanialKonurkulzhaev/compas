"""Нагрузочный прогон GET-запросов: RPS, p50, p95 и HTTP-статусы."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from time import perf_counter
import httpx


async def run(args):
    durations, statuses = [], {}
    remaining = iter(range(args.requests))
    cookies = (
        {"compas_access_token": os.environ["COMPAS_ACCESS_TOKEN"]}
        if os.environ.get("COMPAS_ACCESS_TOKEN")
        else {}
    )
    async with httpx.AsyncClient(
        base_url=args.url,
        timeout=10,
        cookies=cookies,
        limits=httpx.Limits(max_connections=args.concurrency),
    ) as client:

        async def worker():
            for _ in remaining:
                started = perf_counter()
                try:
                    response = await client.get(args.path)
                    status = str(response.status_code)
                except httpx.HTTPError:
                    status = "connection_error"
                statuses[status] = statuses.get(status, 0) + 1
                durations.append(perf_counter() - started)

        started = perf_counter()
        await asyncio.gather(*(worker() for _ in range(args.concurrency)))
        seconds = perf_counter() - started
    durations.sort()
    result = {
        "requests": len(durations),
        "concurrency": args.concurrency,
        "seconds": round(seconds, 3),
        "requests_per_second": round(len(durations) / seconds, 2),
        "statuses": statuses,
        "p50_ms": round(durations[int((len(durations) - 1) * 0.5)] * 1000, 2),
        "p95_ms": round(durations[int((len(durations) - 1) * 0.95)] * 1000, 2),
    }
    print(json.dumps(result, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--path", default="/tests")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.requests < 1 or not 1 <= args.concurrency <= 200:
        parser.error("requests >= 1, concurrency between 1 and 200")
    if not args.path.startswith("/") or args.path.startswith("//"):
        parser.error("path must start with one slash")
    asyncio.run(run(args))
