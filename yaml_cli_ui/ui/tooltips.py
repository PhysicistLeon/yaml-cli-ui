"""Small reusable tooltip helpers for Tk widgets."""

from __future__ import annotations

import tkinter as tk
from typing import Any


class TooltipController:
    def __init__(self, root: tk.Tk, *, delay_ms: int = 450, wraplength_px: int = 480):
        self.root = root
        self.delay_ms = delay_ms
        self.wraplength_px = wraplength_px
        self._window: tk.Toplevel | None = None
        self._active_widget: tk.Widget | None = None
        self._after_id: str | None = None
        self._text: str = ""

    def schedule(self, widget: tk.Widget, text: str) -> None:
        self.hide()
        self._active_widget = widget
        self._text = text
        self._after_id = self.root.after(self.delay_ms, self._show)

    def cancel(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    def hide(self) -> None:
        self.cancel()
        self._active_widget = None
        self._text = ""
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _show(self) -> None:
        self._after_id = None
        if self._active_widget is None or not self._text:
            return

        self._window = tk.Toplevel(self.root)
        self._window.wm_overrideredirect(True)
        x = self._active_widget.winfo_rootx() + 8
        y = self._active_widget.winfo_rooty() + self._active_widget.winfo_height() + 8
        self._window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._window,
            text=self._text,
            justify="left",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=4,
            wraplength=self.wraplength_px,
        )
        label.pack()


def attach_tooltip(controller: TooltipController, widget: tk.Widget, text: Any) -> None:
    if not isinstance(text, str) or not text.strip():
        return
    normalized = text.strip()
    widget.bind("<Enter>", lambda _event, w=widget, t=normalized: controller.schedule(w, t))
    widget.bind("<Leave>", lambda _event: controller.hide())
    widget.bind("<ButtonPress>", lambda _event: controller.hide())
    widget.bind("<FocusOut>", lambda _event: controller.hide())
