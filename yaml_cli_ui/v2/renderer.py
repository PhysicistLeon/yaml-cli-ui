"""Template rendering scaffold for YAML CLI UI v2."""

from __future__ import annotations

from typing import Any

from .models import RunContext


def render_value(value: Any, context: RunContext) -> Any:
    """Render scalar/list/map values with v2 template expressions."""

    raise NotImplementedError(
        "v2 renderer is intentionally deferred in migration scaffold"
    )
