from yaml_cli_ui.ui.log_views import map_step_status, render_step_result_text
from yaml_cli_ui.v2.models import ErrorContext, StepResult, StepStatus


def test_render_step_result_with_nested_children_and_foreach_meta_masks_secrets():
    child = StepResult(
        name="child",
        status=StepStatus.SUCCESS,
        stdout="secret-token",
        stderr="err secret-token",
    )
    root = StepResult(
        name="root",
        status=StepStatus.RECOVERED,
        duration_ms=12,
        children={"child": child},
        meta={"iteration_count": 2, "success_count": 1, "failed_count": 1},
        error=ErrorContext(type="failed", message="boom secret-token"),
    )

    text = render_step_result_text(root, secret_values=["secret-token"])

    assert "root: recovered" in text
    assert "child: success" in text
    assert "foreach: iterations=2" in text
    assert "secret-token" not in text
    assert "******" in text


def test_status_mapping():
    result = StepResult(name="x", status=StepStatus.SUCCESS)
    assert map_step_status(result) == "success"
    result.status = StepStatus.FAILED
    assert map_step_status(result) == "failed"
    result.status = StepStatus.RECOVERED
    assert map_step_status(result) == "recovered"
    result.status = StepStatus.SKIPPED
    assert map_step_status(result) == "idle"
