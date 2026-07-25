"""
key_pool.py — Health-aware API key pool for free-auto model routing.

Only applies to models in FREE_AUTO_MODELS (the 4 CODER_MAP_FREE models).
All other models (go-tier, free-global, direct) are unaffected.

Usage:
    from key_pool import pool

    # At startup
    await pool.probe_all()

    # In forward.py — pick the best healthy key for a model
    key = pool.get_key("mimo-v2.5-free") or fallback_key

    # On 401/429 from upstream
    pool.demote(key, model)

    # Background re-probe loop (run as asyncio task)
    await pool.recheck_loop(interval=60)
"""

import asyncio
import logging

import httpx

from .config import (
    _ANTHROPIC_COMPAT_MODELS,
    FREE_AUTO_MODELS,
    OLLAMA_API_KEYS,
    OLLAMA_URL,
    OPENCODE_FREE_URL,
    UPSTREAM_API_KEYS,
)

logger = logging.getLogger("opencode-proxy")

_PROBE_TIMEOUT = 5.0  # seconds per probe request
_PROBE_CONCURRENCY = 5  # max simultaneous probes


class KeyPool:
    """
    Per-(key, model) health table.

    Health states (stored in _health dict):
      True    -> healthy  (key accepted by upstream for this model)
      False   -> demoted  (key returned 401 or 429)
      absent  -> unknown  (probe inconclusive; treated as healthy for routing)
    """

    def __init__(self, keys: list[str], free_url: str, models: set[str] | frozenset[str]) -> None:
        self._keys: list[str] = keys
        self._free_url: str = free_url.rstrip("/")
        self._models: set[str] | frozenset[str] = models
        self._health: dict[tuple[str, str], bool] = {}
        self._lock = asyncio.Lock()

    # -- Public API -----------------------------------------------------------

    def has_keys(self) -> bool:
        """Return True if at least one key is configured."""
        return bool(self._keys)

    def get_key(self, model: str) -> str | None:
        """
        Return the first healthy (or unknown) key for model.
        Returns None only if ALL keys are explicitly demoted.
        """
        for key in self._keys:
            # absent = unknown = treated as healthy
            if self._health.get((key, model), True):
                return key
        return None

    def demote(self, key: str, model: str) -> None:
        """Mark (key, model) unhealthy. Called on live 401/429."""
        self._health[(key, model)] = False
        logger.warning(
            "key-pool: key[%d] demoted for model=%s",
            self._key_index(key),
            model,
        )

    def promote(self, key: str, model: str) -> None:
        """Restore (key, model) to healthy. Called by recheck_loop."""
        self._health[(key, model)] = True
        logger.info(
            "key-pool: key[%d] restored for model=%s",
            self._key_index(key),
            model,
        )

    def health_snapshot(self) -> dict:
        """
        Return health state keyed by model -> {key_N: status}.
        Raw key values are NEVER included -- only their 1-based indices.
        """
        snap: dict[str, dict[str, str]] = {}
        for model in sorted(self._models):
            snap[model] = {}
            for i, key in enumerate(self._keys, 1):
                state = self._health.get((key, model))
                if state is True:
                    snap[model][f"key_{i}"] = "healthy"
                elif state is False:
                    snap[model][f"key_{i}"] = "demoted"
                else:
                    snap[model][f"key_{i}"] = "unknown"
        return snap

    # -- Startup probe --------------------------------------------------------

    async def probe_all(self) -> None:
        """
        Probe all keys against all FREE_AUTO_MODELS concurrently.
        Called once at startup before the server begins accepting traffic.
        """
        if not self._keys:
            logger.info("key-pool: no keys configured -- pool disabled")
            return
        if not self._free_url:
            logger.warning("key-pool: OPENCODE_FREE_URL not set -- skipping probe")
            return

        models = sorted(self._models)
        total = len(self._keys) * len(models)
        logger.info(
            "key-pool: probing %d keys x %d models (%d probes)...",
            len(self._keys),
            len(models),
            total,
        )

        sem = asyncio.Semaphore(_PROBE_CONCURRENCY)
        async with httpx.AsyncClient() as client:
            tasks = [self._probe_one(client, sem, key, model) for key in self._keys for model in models]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collate results
        summary: dict[str, dict[int, str]] = {m: {} for m in models}
        healthy_count = 0

        for result in results:
            if isinstance(result, Exception):
                logger.debug("key-pool: probe exception: %s", result)
                continue
            key, model, status = result
            idx = self._key_index(key)
            if status == "ok":
                self._health[(key, model)] = True
                summary[model][idx] = "OK"
                healthy_count += 1
            elif status == "demoted":
                self._health[(key, model)] = False
                summary[model][idx] = "FAIL"
            else:
                # 5xx / timeout / network error -- treat as unknown (not demoted)
                summary[model][idx] = "UNKNOWN"
                healthy_count += 1  # optimistically healthy

        # Log one line per model
        for model in models:
            parts = "  ".join(f"key[{i}]={s}" for i, s in sorted(summary[model].items()))
            logger.info("key-pool: %-28s %s", model, parts)

        logger.info("key-pool: probe complete -- %d/%d pairs healthy", healthy_count, total)

    # -- Background re-probe --------------------------------------------------

    async def recheck_loop(self, interval: int = 60) -> None:
        """
        Background asyncio task. Re-probes all demoted (key, model) pairs
        every `interval` seconds and promotes any that now pass.
        """
        while True:
            await asyncio.sleep(interval)
            demoted = [(k, m) for (k, m), ok in list(self._health.items()) if not ok]
            if not demoted:
                continue

            logger.debug("key-pool: re-probing %d demoted pair(s)...", len(demoted))
            try:
                sem = asyncio.Semaphore(_PROBE_CONCURRENCY)
                async with httpx.AsyncClient() as client:
                    tasks = [self._probe_one(client, sem, k, m) for k, m in demoted]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    key, model, status = result
                    if status == "ok":
                        self.promote(key, model)
            except Exception as exc:
                logger.debug("key-pool: recheck error: %s", exc)

    # -- Internal helpers -----------------------------------------------------

    async def _probe_one(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        key: str,
        model: str,
    ) -> tuple[str, str, str]:
        """Probe a single (key, model) pair. Returns (key, model, status).

        OPENCODE_FREE_URL already ends with /zen/v1 so the completions path
        is /chat/completions (not /v1/chat/completions) to avoid duplication.
        """
        async with sem:
            # Avoid /v1/v1/ duplication: FREE_URL already contains /v1
            base = self._free_url
            if base.endswith("/v1"):
                url = f"{base}/chat/completions"
            else:
                url = f"{base}/v1/chat/completions"
            try:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                        "stream": False,
                    },
                    timeout=_PROBE_TIMEOUT,
                )
                if resp.status_code == 200:
                    return key, model, "ok"
                elif resp.status_code >= 400:
                    # Any 4xx or 5xx — demote this key for this model
                    return key, model, "demoted"
                else:
                    return key, model, f"upstream:{resp.status_code}"
            except httpx.TimeoutException:
                return key, model, "timeout"
            except Exception as exc:
                return key, model, f"error:{exc}"

    def _key_index(self, key: str) -> int:
        """1-based index of key in pool (safe to log -- never reveals raw value)."""
        try:
            return self._keys.index(key) + 1
        except ValueError:
            return -1


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

pool = KeyPool(keys=UPSTREAM_API_KEYS, free_url=OPENCODE_FREE_URL, models=FREE_AUTO_MODELS)
ollama_pool = KeyPool(keys=OLLAMA_API_KEYS, free_url=OLLAMA_URL, models=_ANTHROPIC_COMPAT_MODELS)
