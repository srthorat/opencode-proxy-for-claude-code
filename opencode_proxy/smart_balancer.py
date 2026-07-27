"""
opencode-proxy smart_balancer
───────────────────────────────
Predictive Latency-Aware Multi-Provider Load Balancer: Tracks provider latency
and routes prompts to whichever key pool currently has the fastest TTFT response times.
"""
import logging
import time
from typing import Any

logger = logging.getLogger("opencode-proxy.smart_balancer")

_provider_latencies: dict[str, float] = {
    "opencode_free": 0.150,
}


def record_provider_latency(provider_name: str, latency_sec: float) -> None:
    """Update Exponential Moving Average (EMA) latency for a provider."""
    if not provider_name or latency_sec <= 0:
        return
    old_ema = _provider_latencies.get(provider_name, 0.150)
    new_ema = 0.7 * old_ema + 0.3 * latency_sec
    _provider_latencies[provider_name] = round(new_ema, 4)


def get_fastest_provider() -> str:
    """Return the name of the provider with the lowest current latency EMA."""
    best = min(_provider_latencies.items(), key=lambda x: x[1])
    logger.debug("Smart Balancer: Selected fastest provider '%s' (EMA: %.3fs)", best[0], best[1])
    return best[0]


def get_provider_latency_summary() -> dict[str, float]:
    """Return latency summary dict for telemetry dashboard."""
    return dict(_provider_latencies)
