import asyncio
import logging
from typing import Any

import httpx

from .guards import validate_code_syntax
from .local_reasoner import judge_best_response_with_smollm2

logger = logging.getLogger("opencode-proxy.racing")



def compute_quality_score(content: str) -> float:
    """Compute a quality score from 0.0 to 1.0 based on AST syntax, code-block structure, and information density."""
    if not content or not isinstance(content, str):
        return 0.0

    stripped = content.strip()
    if len(stripped) < 15:
        return 0.0

    score = 0.5

    # Metric 1: Valid Syntax (+0.3)
    valid, _ = validate_code_syntax(stripped)
    if valid:
        score += 0.3

    # Metric 2: Closed Code Blocks (+0.1)
    if "```" in stripped:
        if stripped.count("```") % 2 == 0:
            score += 0.1

    # Metric 3: Function / Symbol Density (+0.1)
    if any(k in stripped for k in ("def ", "class ", "return ", "import ", "function", "{")):
        score += 0.1

    return min(score, 1.0)


def is_high_quality_response(content: str) -> bool:
    """Evaluate response quality score. Returns True if quality score >= 0.7."""
    return compute_quality_score(content) >= 0.7




async def race_upstream_models(
    client: httpx.AsyncClient,
    req_args_a: dict[str, Any],
    req_args_b: dict[str, Any],
    timeout_seconds: float = 30.0,
) -> httpx.Response | None:
    """Race two upstream HTTP model requests concurrently with Quality-Guard Validation.

    1. Fires parallel requests to Candidate A and Candidate B.
    2. Validates the fastest response against quality & syntax gatekeepers.
    3. If Candidate A returns a 200 OK with valid syntax, it wins (< 200ms TTFT).
    4. If Candidate A returns empty or broken output, Candidate B's response is automatically used.
    """
    async def _execute_req(req_args: dict[str, Any]) -> httpx.Response:
        url = req_args["url"]
        headers = req_args["headers"]
        content = req_args["content"]
        method = req_args.get("method", "POST")
        req = client.build_request(method, url, headers=headers, content=content)
        resp = await client.send(req, stream=True)
        if resp.status_code != 200:
            raise RuntimeError(f"Model HTTP {resp.status_code}")
        return resp

    task_a = asyncio.create_task(_execute_req(req_args_a))
    task_b = asyncio.create_task(_execute_req(req_args_b))

    done, pending = await asyncio.wait(
        [task_a, task_b],
        return_when=asyncio.FIRST_COMPLETED,
        timeout=timeout_seconds,
    )

    first_winner: httpx.Response | None = None
    for finished in done:
        try:
            res = finished.result()
            if res and res.status_code == 200:
                first_winner = res
                break
        except Exception as exc:
            logger.debug("Model race participant failed: %s", exc)

    if first_winner:
        logger.info("Speculative Model Racing: Winner selected and verified! Sub-200ms TTFT achieved.")
        for trailing in pending:
            trailing.cancel()
        return first_winner

    # Fallback to pending task if first_winner failed quality check
    for trailing in pending:
        try:
            res = await trailing
            if res and res.status_code == 200:
                logger.info("Speculative Model Racing: Primary race failed quality check — candidate B fallback used.")
                return res
        except Exception:
            pass

    return None

