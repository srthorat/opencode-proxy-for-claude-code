import pytest
from opencode_proxy.skills_registry import get_discovered_skills, get_skills_summary


def test_skills_registry_discovery(tmp_path):
    mock_skills_dir = tmp_path / "skills"
    mock_skills_dir.mkdir()

    # Create dummy skill subfolder
    skill_a = mock_skills_dir / "pdf_reader"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text("---\nname: PDF Reader Skill\n---\n# Instructions", encoding="utf-8")

    skill_b = mock_skills_dir / "web_tester"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text("---\nname: Web Tester Skill\n---\n# Instructions", encoding="utf-8")

    discovered = get_discovered_skills(mock_skills_dir)
    assert len(discovered) == 2
    names = [s["name"] for s in discovered]
    assert "PDF Reader Skill" in names
    assert "Web Tester Skill" in names

    summary = get_skills_summary(mock_skills_dir)
    assert summary["skills_count"] == 2
    assert "PDF Reader Skill" in summary["skills_list"]
