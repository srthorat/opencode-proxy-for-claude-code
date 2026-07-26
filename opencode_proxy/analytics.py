"""
opencode-proxy analytics
─────────────────────────
Real-Time Token Savings & Latency Cost Analytics Engine: Tracks cumulative
tokens saved, milliseconds saved via Speculative Model Racing, request volume,
and key rotation efficiency.
"""
import logging
import time
from typing import Any

logger = logging.getLogger("opencode-proxy.analytics")

_start_time = time.time()
_total_requests = 0
_total_chars_saved = 0
_total_ms_saved = 0.0
_cache_hits = 0


def record_request() -> None:
    global _total_requests
    _total_requests += 1


def record_token_savings(saved_chars: int) -> None:
    global _total_chars_saved
    if saved_chars > 0:
        _total_chars_saved += saved_chars


def record_race_latency_saved(ms_saved: float) -> None:
    global _total_ms_saved
    if ms_saved > 0:
        _total_ms_saved += ms_saved


def record_cache_hit() -> None:
    global _cache_hits
    _cache_hits += 1


def get_analytics_summary() -> dict[str, Any]:
    uptime = round(time.time() - _start_time, 1)
    approx_tokens_saved = int(_total_chars_saved / 3.5)
    return {
        "uptime_seconds": uptime,
        "total_requests": _total_requests,
        "cache_hits": _cache_hits,
        "chars_saved": _total_chars_saved,
        "approx_tokens_saved": approx_tokens_saved,
        "total_ms_saved_by_racing": round(_total_ms_saved, 1),
        "estimated_cost_saved_usd": round(approx_tokens_saved * 0.000003, 4),
    }
