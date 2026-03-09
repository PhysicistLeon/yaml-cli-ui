"""Small reusable tooltip helpers for Tk widgets."""

from __future__ import annotations

from typing import Any
import tkinter as tk


TOOLTIP_DELAY_MS = 300
TOOLTIP_WRAPLENGTH_PX = 480


class TooltipController:
    def __init__(
        self,
        root: tk.Tk,
        *,
        delay_ms: int = TOOLTIP_DELAY_MS,
        wraplength_px: int = TOOLTIP_WRAPLENGTH_PX,
    ):
        self.root = root
        self.delay_ms = delay_ms
        self.wraplength_px = wraplength_px
        self._window: tk.Toplevel | None = None
        self._active_widget: tk.Widget | None = None
        self._after_id: str | None = None
        self._text = ""

    def schedule(self, widget: tk.Widget, text: str) -> None:
        self.hide()
        self._active_widget = widget
        self._text = text
        self._after_id = self.root.after(self.delay_ms, self._show)

    def hide(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._active_widget = None
        self._text = ""
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _show(self) -> None:
        self._after_id = None
        if self._active_widget is None:
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


def normalize_tooltip_text(raw_text: Any) -> str | None:
    if not isinstance(raw_text, str):
        return None
    text = raw_text.strip()
    return text or None
