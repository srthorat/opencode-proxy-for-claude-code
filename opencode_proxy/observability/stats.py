import time
from collections import Counter, deque

_start_time = time.monotonic()
_total = 0
_by_model: Counter = Counter()
_by_status: Counter = Counter()
_latencies: deque = deque(maxlen=1000)


def record(model: str, status: int, latency_ms: int) -> None:
    global _total
    _total += 1
    if model:
        _by_model[model] += 1
    if 200 <= status < 300:
        _by_status["2xx"] += 1
    elif 400 <= status < 500:
        _by_status["4xx"] += 1
    elif status >= 500:
        _by_status["5xx"] += 1
    _latencies.append(latency_ms)


def snapshot() -> dict:
    lats = sorted(_latencies)
    n = len(lats)

    def pct(p: float) -> int:
        return lats[int(n * p)] if n else 0

    return {
        "uptime_seconds": int(time.monotonic() - _start_time),
        "total_requests": _total,
        "by_model": dict(_by_model.most_common()),
        "by_status": dict(_by_status),
        "p50_latency_ms": pct(0.50),
        "p95_latency_ms": pct(0.95),
        "p99_latency_ms": pct(0.99),
    }
