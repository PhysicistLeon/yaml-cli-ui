"""Exception hierarchy for YAML CLI UI v2 scaffold."""


class V2Error(Exception):
    """Base class for all v2-related errors."""


class V2LoadError(V2Error):
    """Raised when v2 document loading fails."""


class V2ValidationError(V2Error):
    """Raised when v2 document validation fails."""


class V2ExpressionError(V2Error):
    """Raised when v2 expression parsing/evaluation fails."""


class V2ExecutionError(V2Error):
    """Raised when v2 execution fails."""
