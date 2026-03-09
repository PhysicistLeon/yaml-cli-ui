from yaml_cli_ui.ui.tooltips import attach_tooltip


class DummyWidget:
    def __init__(self):
        self.bound = {}

    def bind(self, event, handler):
        self.bound[event] = handler


class DummyController:
    def __init__(self):
        self.calls = []

    def schedule(self, widget, text):
        self.calls.append((widget, text))

    def hide(self):
        self.calls.append(("hide", None))


def test_attach_tooltip_binds_events_for_non_empty_text():
    controller = DummyController()
    widget = DummyWidget()

    attach_tooltip(controller, widget, "  info text  ")

    assert set(widget.bound.keys()) == {"<Enter>", "<Leave>", "<ButtonPress>", "<FocusOut>"}


def test_attach_tooltip_skips_empty_or_non_string_text():
    controller = DummyController()
    widget = DummyWidget()

    attach_tooltip(controller, widget, "   ")
    attach_tooltip(controller, widget, None)

    assert widget.bound == {}
