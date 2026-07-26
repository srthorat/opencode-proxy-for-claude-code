import pytest
from opencode_proxy.distiller import compress_tool_result_content, distill_payload_messages


def test_compress_tool_result_content_ansi():
    raw_log = "\x1b[31mError:\x1b[0m Failed test run\n\n\n\nDone."
    cleaned = compress_tool_result_content(raw_log)
    assert "\x1b[31m" not in cleaned
    assert "Error: Failed test run\n\nDone." in cleaned


def test_compress_tool_result_content_truncation():
    huge_text = "A" * 5000
    compressed = compress_tool_result_content(huge_text, max_chars=1000)
    assert len(compressed) < 5000
    assert "truncated by opencode-proxy Token Distiller" in compressed


def test_distill_payload_messages():
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": "B" * 6000,
                    }
                ],
            }
        ]
    }
    distill_payload_messages(payload, max_chars=3000)
    compressed_text = payload["messages"][0]["content"][0]["content"]
    assert len(compressed_text) < 6000
    assert "Token Distiller" in compressed_text


def test_caveman_compression():
    from opencode_proxy.distiller import compress_system_prompt_caveman

    verbose_sys = "Please prioritize verifiable implementations with automated unit tests and avoid plain-text secret exposure, validate external inputs, and enforce safe defaults."
    compressed = compress_system_prompt_caveman(verbose_sys)
    assert "Verifiable code. Auto unit tests." in compressed
    assert "Zero raw secrets. Validate inputs. Safe defaults." in compressed

