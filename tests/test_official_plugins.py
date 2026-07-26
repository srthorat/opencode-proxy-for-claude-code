import json
import pytest
from opencode_proxy.skills_registry import get_discovered_plugins, get_skills_summary


def test_official_plugins_discovery(tmp_path):
    mock_plugins_dir = tmp_path / "plugins"
    mock_plugins_dir.mkdir()

    # Create dummy plugin folder structure
    plugin_a = mock_plugins_dir / "official_code_reviewer" / ".claude-plugin"
    plugin_a.mkdir(parents=True)
    (plugin_a / "plugin.json").write_text(
        json.dumps({"name": "official-code-reviewer", "version": "2.0.0", "description": "Code Reviewer Plugin"}),
        encoding="utf-8",
    )

    plugin_b = mock_plugins_dir / "official_security_auditor" / ".claude-plugin"
    plugin_b.mkdir(parents=True)
    (plugin_b / "plugin.json").write_text(
        json.dumps({"name": "official-security-auditor", "version": "1.5.0", "description": "Security Auditor Plugin"}),
        encoding="utf-8",
    )

    discovered = get_discovered_plugins(mock_plugins_dir)
    assert len(discovered) == 2
    names = [p["name"] for p in discovered]
    assert "official-code-reviewer" in names
    assert "official-security-auditor" in names

    summary = get_skills_summary(plugins_path=mock_plugins_dir)
    assert summary["official_plugins_count"] == 2
    assert "official-code-reviewer" in summary["official_plugins_list"]
