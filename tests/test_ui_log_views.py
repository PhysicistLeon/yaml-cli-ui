from datetime import datetime

from yaml_cli_ui.ui.log_views import render_step_result
from yaml_cli_ui.v2.models import ErrorContext, StepResult, StepStatus


def test_render_step_result_nested_pipeline_and_foreach():
    child = StepResult(name="child", status=StepStatus.SUCCESS, duration_ms=5)
    foreach = StepResult(name="foreach_item", status=StepStatus.SUCCESS, children={"nested": child})
    root = StepResult(name="root", status=StepStatus.RECOVERED, children={"foreach": foreach}, started_at=datetime.now())

    text = render_step_result(root)

    assert "root: recovered" in text
    assert "foreach_item: success" in text
    assert "child: success" in text


def test_render_step_result_redacts_secrets():
    result = StepResult(
        name="cmd",
        status=StepStatus.FAILED,
        stdout="token=ABC123",
        stderr="err ABC123",
        error=ErrorContext(type="execution_failed", message="ABC123 leaked"),
    )

    text = render_step_result(result, secrets=["ABC123"])

    assert "ABC123" not in text
    assert "******" in text
