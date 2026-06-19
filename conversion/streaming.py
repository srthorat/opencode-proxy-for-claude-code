import json
import logging
import uuid
from typing import Optional

from conversion import STOP_REASON_MAP

logger = logging.getLogger("opencode-proxy")


async def _openai_stream_to_anthropic(upstream_resp, model: str):
    """Yield Anthropic-format SSE bytes from an OpenAI streaming response.

    Properly converts both text and tool_call deltas so Claude Code can parse
    tool invocations from OpenAI-compat models (kimi, deepseek, mimo, etc.).

    Anthropic SSE contract for tool_use:
      content_block_start  → {type:"tool_use", id, name, input:{}}
      content_block_delta  → {type:"input_json_delta", partial_json: "..."}
      content_block_stop

    message_stop is emitted unconditionally at the end of the generator so
    Anthropic clients never hang, even if the upstream connection drops
    mid-stream (P0 #4).
    """
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    yield (
        f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n"
    ).encode()
    yield b"event: ping\ndata: {\"type\":\"ping\"}\n\n"

    stop_reason = "end_turn"
    output_tokens = 0  # P0 #2: accumulate from usage chunks

    # Block tracking — we open blocks lazily so tool-only responses don't emit
    # a spurious empty text block that confuses strict clients.
    text_block_idx: Optional[int] = None
    # oai_tool_index -> {"anthr_idx": int, "open": bool}
    tool_blocks: dict = {}
    next_idx = 0

    buffer = b""
    # P0 #4: wrap the aiter_bytes loop in try/except so that a network error
    # or unexpected exception does not prevent message_stop from being emitted.
    try:
        async for chunk in upstream_resp.aiter_bytes():
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line or line == b"data: [DONE]":
                    continue
                if not line.startswith(b"data: "):
                    continue
                try:
                    obj = json.loads(line[6:])
                    choice = (obj.get("choices") or [{}])[0]
                    delta = choice.get("delta", {})

                    # ── Text content ──────────────────────────────────────────
                    text = delta.get("content") or ""
                    if text:
                        if text_block_idx is None:
                            text_block_idx = next_idx
                            next_idx += 1
                            yield (
                                f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': text_block_idx, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
                            ).encode()
                        yield (
                            f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': text_block_idx, 'delta': {'type': 'text_delta', 'text': text}})}\n\n"
                        ).encode()

                    # ── Tool calls ────────────────────────────────────────────
                    tcs = delta.get("tool_calls")
                    if tcs:
                        for tc in tcs:
                            oai_idx = tc.get("index", 0)
                            fn = tc.get("function", {})

                            if oai_idx not in tool_blocks:
                                # First chunk for this tool call carries id + name
                                tc_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:8]}"
                                tc_name = fn.get("name") or ""
                                anthr_idx = next_idx
                                next_idx += 1
                                tool_blocks[oai_idx] = {"anthr_idx": anthr_idx, "open": True}
                                yield (
                                    f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': anthr_idx, 'content_block': {'type': 'tool_use', 'id': tc_id, 'name': tc_name, 'input': {}}})}\n\n"
                                ).encode()

                            arg_chunk = fn.get("arguments") or ""
                            if arg_chunk:
                                anthr_idx = tool_blocks[oai_idx]["anthr_idx"]
                                yield (
                                    f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': anthr_idx, 'delta': {'type': 'input_json_delta', 'partial_json': arg_chunk}})}\n\n"
                                ).encode()

                    # ── Usage — accumulate output_tokens (P0 #2) ─────────────
                    usage = obj.get("usage")
                    if usage:
                        output_tokens = usage.get("completion_tokens", output_tokens)

                    fr = choice.get("finish_reason")
                    if fr:
                        stop_reason = STOP_REASON_MAP.get(fr, "end_turn")
                except Exception as exc:
                    # Mid-stream JSON parse errors are expected (e.g. keep-alive
                    # comments, malformed chunks).  Log and skip — the loop
                    # continues and message_stop is still guaranteed below.
                    logger.warning("SSE parse error (chunk skipped): %s", exc)
    except Exception as exc:
        # Network-level read error.  Log it and fall through so that the
        # close-blocks and message_stop yields below always fire (P0 #4).
        logger.warning("SSE stream read error (message_stop will still be emitted): %s", exc)

    # ── Close all open blocks ─────────────────────────────────────────────
    # These are emitted unconditionally so message_stop always fires even if
    # the upstream connection dropped mid-stream.
    if text_block_idx is not None:
        yield (
            f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': text_block_idx})}\n\n"
        ).encode()
    for tb in tool_blocks.values():
        yield (
            f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': tb['anthr_idx']})}\n\n"
        ).encode()
    # Guarantee at least one block was emitted (Anthropic clients expect it)
    if text_block_idx is None and not tool_blocks:
        yield (
            f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
        ).encode()
        yield (
            f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
        ).encode()

    # P0 #2: emit real output_tokens (accumulated above) instead of hard-coded 0
    yield (
        f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"
    ).encode()
    yield (
        f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
    ).encode()
