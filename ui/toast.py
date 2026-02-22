from __future__ import annotations

from gi.repository import GLib, Gtk


class ToastOverlay(Gtk.Overlay):
    def __init__(self, child: Gtk.Widget) -> None:
        super().__init__()
        self.set_child(child)

        self._dismiss_id: int | None = None
        self._hide_id: int | None = None

        self._toast_label = Gtk.Label(xalign=0.5)
        self._toast_label.set_wrap(True)

        self._toast_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._toast_box.add_css_class("toast")
        self._toast_box.add_css_class("toast-hidden")
        self._toast_box.set_visible(False)
        self._toast_box.append(self._toast_label)

        self._toast_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0,
        )
        self._toast_container.set_halign(Gtk.Align.CENTER)
        self._toast_container.set_valign(Gtk.Align.END)
        self._toast_container.set_hexpand(True)
        self._toast_container.set_vexpand(True)
        self._toast_container.append(self._toast_box)

        self.add_overlay(self._toast_container)

    def show_toast(
        self,
        message: str,
        *,
        is_error: bool = False,
        duration_ms: int = 3000,
    ) -> None:
        if self._dismiss_id is not None:
            GLib.source_remove(self._dismiss_id)
            self._dismiss_id = None
        if self._hide_id is not None:
            GLib.source_remove(self._hide_id)
            self._hide_id = None

        self._toast_label.set_label(message)
        if is_error:
            self._toast_box.add_css_class("toast-error")
        else:
            self._toast_box.remove_css_class("toast-error")
        self._toast_box.set_visible(True)
        self._toast_box.remove_css_class("toast-hidden")

        self._dismiss_id = GLib.timeout_add(
            max(250, int(duration_ms)),
            self._begin_hide,
        )

    def _begin_hide(self) -> bool:
        self._dismiss_id = None
        self._toast_box.add_css_class("toast-hidden")
        self._hide_id = GLib.timeout_add(220, self._finish_hide)
        return False

    def _finish_hide(self) -> bool:
        self._hide_id = None
        self._toast_box.set_visible(False)
        return False


def show_toast(
    app,
    message: str,
    is_error: bool = False,
    duration_ms: int = 3000,
) -> None:
    overlay = getattr(app, "toast_overlay", None)
    if overlay is None:
        return
    if not isinstance(overlay, ToastOverlay):
        return
    overlay.show_toast(
        message,
        is_error=is_error,
        duration_ms=duration_ms,
    )
