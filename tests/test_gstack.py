from opencode_proxy.personas import get_gstack_workflow_summary


def test_gstack_workflow_summary():
    summary = get_gstack_workflow_summary()
    assert "GSTACK ENGINEERING WORKFLOW GUIDELINES" in summary
    assert "CEO / Product Review" in summary
    assert "Eng Review" in summary
    assert "Security Review" in summary
    assert "QA & Testing" in summary
