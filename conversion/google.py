import json
import logging
import uuid

logger = logging.getLogger("opencode-proxy")

STOP_REASON_MAP = {
    "STOP": "end_turn",
    "MAX_TOKENS": "max_tokens",
    "STOP_SEQUENCE": "stop_sequence",
}


def _find_tool_name_by_id(messages: list, tool_use_id: str) -> str:
    """Scan messages history to find the function name associated with tool_use_id."""
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if (
                    isinstance(b, dict)
                    and b.get("type") == "tool_use"
                    and b.get("id") == tool_use_id
                ):
                    return b.get("name", "")
    return "unknown_tool"


def _anthropic_to_google(payload: dict) -> dict:
    """Convert an Anthropic Messages API payload to Google GenAI REST API format."""
    messages_list = payload.get("messages", [])
    
    # 1. System Instruction
    system = payload.get("system")
    system_instruction = None
    if system:
        if isinstance(system, str):
            system_instruction = {"parts": [{"text": system}]}
        elif isinstance(system, list):
            parts = []
            for b in system:
                if isinstance(b, dict) and b.get("type") == "text":
                    parts.append({"text": b.get("text", "")})
            if parts:
                system_instruction = {"parts": parts}

    # 2. Contents (Messages)
    contents = []
    for msg in messages_list:
        role = msg.get("role", "user")
        # Google expects "user" or "model"
        google_role = "model" if role == "assistant" else "user"
        content = msg.get("content", "")
        parts = []

        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    parts.append({"text": block.get("text", "")})
                elif btype == "image":
                    src = block.get("source", {})
                    if src.get("type") == "base64":
                        parts.append({
                            "inlineData": {
                                "mimeType": src.get("media_type", "image/jpeg"),
                                "data": src.get("data", "")
                            }
                        })
                elif btype == "tool_use":
                    parts.append({
                        "functionCall": {
                            "name": block.get("name", ""),
                            "args": block.get("input", {})
                        }
                    })
                elif btype == "tool_result":
                    tool_use_id = block.get("tool_use_id", "")
                    tool_name = _find_tool_name_by_id(messages_list, tool_use_id)
                    content_val = block.get("content")
                    
                    if isinstance(content_val, list):
                        text_str = "\n".join(
                            b.get("text", "") for b in content_val
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        text_str = str(content_val)
                    
                    # Wrap output in a JSON object since Gemini expects a structured response
                    parts.append({
                        "functionResponse": {
                            "name": tool_name,
                            "response": {"result": text_str}
                        }
                    })
        
        if parts:
            contents.append({"role": google_role, "parts": parts})

    # 3. Tools
    tools_list = []
    if "tools" in payload:
        function_declarations = []
        for t in payload["tools"]:
            function_declarations.append({
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {})
            })
        if function_declarations:
            tools_list.append({"functionDeclarations": function_declarations})

    # 4. Generation Config
    generation_config = {}
    if "max_tokens" in payload:
        generation_config["maxOutputTokens"] = payload["max_tokens"]
    if "temperature" in payload:
        generation_config["temperature"] = payload["temperature"]
    if "top_p" in payload:
        generation_config["topP"] = payload["top_p"]
    if "stop_sequences" in payload:
        generation_config["stopSequences"] = payload["stop_sequences"]

    # Thinking mode support
    thinking = payload.get("thinking")
    if thinking and isinstance(thinking, dict) and thinking.get("type") == "enabled":
        budget = thinking.get("budget_tokens", 1024)
        generation_config["thinkingConfig"] = {
            "thinkingBudget": budget
        }

    # Assemble request payload
    google_payload = {"contents": contents}
    if system_instruction:
        google_payload["systemInstruction"] = system_instruction
    if tools_list:
        google_payload["tools"] = tools_list
    if generation_config:
        google_payload["generationConfig"] = generation_config

    # Tool Choice Config
    if "tool_choice" in payload:
        tc = payload["tool_choice"]
        if isinstance(tc, dict):
            ttype = tc.get("type")
            if ttype == "auto":
                google_payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
            elif ttype == "any":
                google_payload["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}
            elif ttype == "disabled":
                google_payload["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
            elif ttype == "tool" and "name" in tc:
                google_payload["toolConfig"] = {
                    "functionCallingConfig": {
                        "mode": "ANY",
                        "allowedFunctionNames": [tc["name"]]
                    }
                }

    return google_payload


def _google_to_anthropic(resp: dict, model: str) -> dict:
    """Convert a Google GenAI REST response body to Anthropic Messages format."""
    candidates = resp.get("candidates") or [{}]
    choice = candidates[0]
    content_obj = choice.get("content") or {}
    parts = content_obj.get("parts") or []

    content_blocks = []
    for part in parts:
        if "text" in part:
            content_blocks.append({"type": "text", "text": part["text"]})
        elif "functionCall" in part:
            fc = part["functionCall"]
            content_blocks.append({
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex[:24]}",
                "name": fc.get("name", ""),
                "input": fc.get("args", {})
            })

    finish_reason = choice.get("finishReason", "STOP")
    stop_reason = STOP_REASON_MAP.get(finish_reason, "end_turn")

    usage = resp.get("usageMetadata", {})
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0),
        },
    }


async def _google_stream_to_anthropic(upstream_resp, model: str):
    """Yield Anthropic-format SSE bytes from a Google streaming response."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    yield (
        f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n"
    ).encode()
    yield b"event: ping\ndata: {\"type\":\"ping\"}\n\n"

    stop_reason = "end_turn"
    output_tokens = 0
    text_block_idx = None
    next_idx = 0

    buffer = b""
    try:
        async for chunk in upstream_resp.aiter_bytes():
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                if line.startswith(b"data: "):
                    line = line[6:]
                try:
                    obj = json.loads(line)
                    candidates = obj.get("candidates") or [{}]
                    choice = candidates[0]
                    content_obj = choice.get("content") or {}
                    parts = content_obj.get("parts") or []

                    # Process Parts
                    for part in parts:
                        if "text" in part:
                            text = part["text"]
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

                        elif "functionCall" in part:
                            fc = part["functionCall"]
                            tc_name = fc.get("name", "")
                            tc_id = f"toolu_{uuid.uuid4().hex[:24]}"
                            anthr_idx = next_idx
                            next_idx += 1

                            # Emit start, delta, and stop immediately for complete function calls
                            yield (
                                f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': anthr_idx, 'content_block': {'type': 'tool_use', 'id': tc_id, 'name': tc_name, 'input': {}}})}\n\n"
                            ).encode()
                            yield (
                                f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': anthr_idx, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(fc.get('args', {}))}})}\n\n"
                            ).encode()
                            yield (
                                f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': anthr_idx})}\n\n"
                            ).encode()

                    # Extract metadata
                    usage = obj.get("usageMetadata")
                    if usage:
                        output_tokens = usage.get("candidatesTokenCount", output_tokens)

                    fr = choice.get("finishReason")
                    if fr:
                        stop_reason = STOP_REASON_MAP.get(fr, "end_turn")

                except Exception as exc:
                    logger.warning("SSE parse error (chunk skipped): %s", exc)
    except Exception as exc:
        logger.warning("SSE stream read error: %s", exc)

    # Close open blocks
    if text_block_idx is not None:
        yield (
            f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': text_block_idx})}\n\n"
        ).encode()

    # Guarantee at least one block was emitted
    if text_block_idx is None and next_idx == 0:
        yield (
            f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
        ).encode()
        yield (
            f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
        ).encode()

    yield (
        f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"
    ).encode()
    yield (
        f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
    ).encode()
