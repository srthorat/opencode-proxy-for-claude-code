import json
from typing import Any



def _anthropic_to_openai(payload: dict) -> dict:
    """Convert an Anthropic Messages API payload to OpenAI Chat Completions format."""
    oai: dict = {"model": payload.get("model", "")}
    messages: list[dict[str, Any]] = []

    system = payload.get("system")
    if system:
        if isinstance(system, str):
            messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text = "\n".join(
                b.get("text", "") for b in system
                if isinstance(b, dict) and b.get("type") == "text"
            )
            if text:
                messages.append({"role": "system", "content": text})

    for msg in payload.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            messages.append({"role": role, "content": str(content)})
            continue

        # Separate block types
        text_blocks        = [b for b in content if b.get("type") == "text"]
        tool_use_blocks    = [b for b in content if b.get("type") == "tool_use"]
        tool_result_blocks = [b for b in content if b.get("type") == "tool_result"]
        image_blocks       = [b for b in content if b.get("type") == "image"]

        # Tool results → OpenAI tool messages
        if tool_result_blocks:
            for b in tool_result_blocks:
                rc = b.get("content", "")
                if isinstance(rc, list):
                    rc = " ".join(
                        rb.get("text", "") for rb in rc if rb.get("type") == "text"
                    )
                messages.append({
                    "role": "tool",
                    "tool_call_id": b.get("tool_use_id", ""),
                    "content": str(rc),
                })
            # Preserve any accompanying text blocks as a separate user message so
            # they are not silently dropped by the continue below.
            if text_blocks:
                extra_text = " ".join(b.get("text", "") for b in text_blocks).strip()
                if extra_text:
                    messages.append({"role": "user", "content": extra_text})
            continue

        # Tool calls → assistant message with tool_calls
        if tool_use_blocks:
            tool_calls = [
                {
                    "id": b.get("id", f"call_{i}"),
                    "type": "function",
                    "function": {
                        "name": b.get("name", ""),
                        "arguments": json.dumps(b.get("input", {})),
                    },
                }
                for i, b in enumerate(tool_use_blocks)
            ]
            text = " ".join(b.get("text", "") for b in text_blocks).strip()
            oai_msg: dict = {"role": role, "content": text or None, "tool_calls": tool_calls}
            messages.append(oai_msg)
            continue

        # Build multipart content for text + images
        oai_parts = []
        for b in text_blocks:
            oai_parts.append({"type": "text", "text": b.get("text", "")})
        for b in image_blocks:
            src = b.get("source", {})
            if src.get("type") == "base64":
                oai_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            f"data:{src.get('media_type', 'image/jpeg')};"
                            f"base64,{src.get('data', '')}"
                        )
                    },
                })
            elif src.get("type") == "url":
                oai_parts.append({"type": "image_url", "image_url": {"url": src.get("url", "")}})

        if len(oai_parts) == 1 and oai_parts[0]["type"] == "text":
            messages.append({"role": role, "content": oai_parts[0]["text"]})
        elif oai_parts:
            messages.append({"role": role, "content": oai_parts})
        else:
            messages.append({"role": role, "content": ""})

    oai["messages"] = messages

    for key in (
        "max_tokens", "temperature", "top_p", "stream", "stop", "n",
        "presence_penalty", "frequency_penalty", "seed",
    ):
        if key in payload:
            oai[key] = payload[key]

    if "tools" in payload:
        oai["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in payload["tools"]
        ]

    if "tool_choice" in payload:
        tc = payload["tool_choice"]
        if isinstance(tc, dict):
            ttype = tc.get("type")
            if ttype == "auto":
                oai["tool_choice"] = "auto"
            elif ttype == "any":
                oai["tool_choice"] = "required"
            elif ttype == "disabled":
                oai["tool_choice"] = "none"  # OpenAI equivalent of Anthropic "disabled"
            elif ttype == "tool" and "name" in tc:
                oai["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}
            else:
                oai["tool_choice"] = "auto"

    return oai
