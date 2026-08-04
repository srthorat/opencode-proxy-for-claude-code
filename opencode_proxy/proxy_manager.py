from __future__ import annotations

import asyncio
import logging
import random
import httpx
from .config import AUTO_PROXY_URL, OUTBOUND_PROXIES

logger = logging.getLogger("opencode-proxy")

_master_proxies: set[str] = set()
_used_proxies: set[str] = set()
_refill_lock = asyncio.Lock()

async def _check_proxy(proxy_url: str) -> str | None:
    """Checks if a proxy is alive by doing a fast HEAD request to google."""
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=5.0) as client:
            resp = await client.head("https://www.google.com")
            if resp.status_code in (200, 204):
                return proxy_url
    except Exception:
        pass
    return None

async def _fetch_master_list():
    """Fetches the raw proxy list from the source and populates the master list."""
    if not AUTO_PROXY_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(AUTO_PROXY_URL)
            resp.raise_for_status()
            
            lines = resp.text.splitlines()
            new_count = 0
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("http://") and not line.startswith("socks"):
                    line = f"http://{line}"
                if line not in _master_proxies:
                    _master_proxies.add(line)
                    new_count += 1
                    
            if new_count > 0:
                logger.info("Auto-Proxy: Fetched %d new proxies into master list (total %d)", new_count, len(_master_proxies))
    except Exception as exc:
        logger.warning("Auto-Proxy: Failed to fetch proxies from %s: %s", AUTO_PROXY_URL, exc)

async def refill_pool(count: int = 10):
    """Fills the OUTBOUND_PROXIES pool with up to `count` fresh, healthy proxies."""
    if not AUTO_PROXY_URL:
        return
        
    async with _refill_lock:
        needed = count - len(OUTBOUND_PROXIES)
        if needed <= 0:
            return
            
        # Refetch if we have exhausted the master list
        available = list(_master_proxies - _used_proxies - set(OUTBOUND_PROXIES))
        if not available:
            logger.info("Auto-Proxy: Master list exhausted. Fetching fresh list...")
            await _fetch_master_list()
            available = list(_master_proxies - _used_proxies - set(OUTBOUND_PROXIES))
            if not available:
                logger.warning("Auto-Proxy: No more fresh proxies available!")
                return
                
        random.shuffle(available)
        
        # Test in batches to find enough healthy ones
        healthy_found = []
        batch_size = max(50, needed * 5)
        for i in range(0, len(available), batch_size):
            batch = available[i:i+batch_size]
            logger.info("Auto-Proxy: Testing batch of %d random proxies...", len(batch))
            results = await asyncio.gather(*[_check_proxy(p) for p in batch])
            
            for p in results:
                if p is not None:
                    healthy_found.append(p)
                    if len(healthy_found) >= needed:
                        break
            
            if len(healthy_found) >= needed:
                break
                
        if healthy_found:
            OUTBOUND_PROXIES.extend(healthy_found)
            logger.info("Auto-Proxy: Added %d healthy proxies to rotation pool (total in pool: %d).", len(healthy_found), len(OUTBOUND_PROXIES))
        else:
            logger.warning("Auto-Proxy: Could not find enough healthy proxies in this scan.")

def ban_proxy(proxy_url: str):
    """Removes a proxy from the active pool and marks it as used (e.g. on 429)."""
    if proxy_url in OUTBOUND_PROXIES:
        OUTBOUND_PROXIES.remove(proxy_url)
    _used_proxies.add(proxy_url)
    logger.info("Auto-Proxy: Banned proxy %s (total active: %d, total banned: %d)", proxy_url, len(OUTBOUND_PROXIES), len(_used_proxies))
    
    # If we run dry, schedule a background refill
    if len(OUTBOUND_PROXIES) == 0:
        logger.warning("Auto-Proxy: Active pool is empty! Triggering background refill...")
        asyncio.create_task(refill_pool(10))

async def init_proxies():
    """Initial synchronous fetch and load of proxies before app starts."""
    await _fetch_master_list()
    await refill_pool(10)

async def proxy_updater_task():
    """Background task to fetch fresh master lists periodically."""
    while True:
        await asyncio.sleep(1800)  # 30 minutes
        await _fetch_master_list()
        
        # If pool is low, refill it
        if len(OUTBOUND_PROXIES) < 10:
            await refill_pool(10)
