"""Expression parsing/evaluation scaffold for YAML CLI UI v2."""

from __future__ import annotations

from typing import Any

from .models import RunContext


def evaluate_expression(expression: str, context: RunContext) -> Any:
    """Evaluate a v2 expression against runtime context."""

    raise NotImplementedError(
        "v2 expression evaluator is intentionally deferred in migration scaffold"
    )
