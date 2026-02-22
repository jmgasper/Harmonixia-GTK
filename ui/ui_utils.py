import logging
import os
import platform
import socket

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
PangoCairo = None
try:
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import PangoCairo
except (ImportError, ValueError):
    PangoCairo = None

from gi.repository import Gdk, Gtk, Pango


def load_custom_fonts(font_paths: list[str]) -> None:
    if PangoCairo is None:
        return
    font_map = PangoCairo.FontMap.get_default()
    if not font_map or not hasattr(font_map, "add_font_file"):
        return
    logger = logging.getLogger(__name__)
    for path in font_paths:
        if not os.path.isfile(path):
            logger.warning("Font file missing: %s", path)
            continue
        try:
            loaded = font_map.add_font_file(path)
        except Exception as exc:
            logger.warning("Failed to load font %s: %s", path, exc)
            continue
        if not loaded:
            logger.warning("Font file rejected: %s", path)


def apply_css(css_path: str) -> None:
    provider = Gtk.CssProvider()
    try:
        with open(css_path, "r", encoding="utf-8") as handle:
            css = handle.read()
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Failed to load CSS from %s: %s",
            css_path,
            exc,
        )
        return
    provider.load_from_data(css.encode("utf-8"))
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def clear_container(container: Gtk.Widget) -> None:
    child = container.get_first_child()
    while child:
        detach_context_popovers(child)
        container.remove(child)
        child = container.get_first_child()


def detach_context_popover(widget: Gtk.Widget) -> None:
    popover = getattr(widget, "context_popover", None)
    if popover is None:
        return
    try:
        popover.popdown()
    except Exception:
        pass
    try:
        if popover.get_parent() is widget:
            popover.unparent()
    except Exception:
        pass
    widget.context_popover = None


def detach_context_popovers(widget: Gtk.Widget) -> None:
    stack = [widget]
    while stack:
        current = stack.pop()
        detach_context_popover(current)
        child = current.get_first_child()
        while child is not None:
            stack.append(child)
            child = child.get_next_sibling()


def attach_context_popover(anchor: Gtk.Widget, popover: Gtk.Popover) -> None:
    popover.set_parent(anchor)
    anchor.context_popover = popover

    def _on_parent_changed(widget: Gtk.Widget, _pspec: object) -> None:
        if widget.get_parent() is None:
            detach_context_popover(widget)

    anchor.connect("notify::parent", _on_parent_changed)


def configure_media_flowbox(
    flow: Gtk.FlowBox,
    selection_mode: Gtk.SelectionMode,
    *,
    min_children_per_line: int = 2,
    max_children_per_line: int = 6,
    column_spacing: int = 16,
    row_spacing: int = 16,
    homogeneous: bool = True,
    css_class: str | None = "search-grid",
) -> None:
    if css_class:
        flow.add_css_class(css_class)
    flow.set_homogeneous(homogeneous)
    flow.set_min_children_per_line(min_children_per_line)
    flow.set_max_children_per_line(max_children_per_line)
    flow.set_selection_mode(selection_mode)
    flow.set_activate_on_single_click(True)
    flow.set_halign(Gtk.Align.FILL)
    flow.set_valign(Gtk.Align.START)
    flow.set_hexpand(True)
    flow.set_vexpand(False)
    flow.set_column_spacing(column_spacing)
    flow.set_row_spacing(row_spacing)


def format_artist_names(artists: list) -> str:
    names = []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or artist.get("sort_name")
        else:
            name = str(artist)
        if name:
            names.append(name)

    if not names:
        return "Unknown Artist"
    if len(names) > 2:
        return f"{names[0]}, {names[1]} +{len(names) - 2}"
    return ", ".join(names)


def get_local_device_names() -> set[str]:
    names = set()
    for candidate in (
        socket.gethostname(),
        platform.node(),
        os.getenv("HOSTNAME", ""),
    ):
        if not candidate:
            continue
        cleaned = candidate.strip()
        if not cleaned:
            continue
        normalized = cleaned.casefold()
        names.add(normalized)
        short = cleaned.split(".")[0].casefold()
        if short:
            names.add(short)
    return names


def get_gtk_environment_info() -> tuple[str, str]:
    version = (
        f"{Gtk.get_major_version()}."
        f"{Gtk.get_minor_version()}."
        f"{Gtk.get_micro_version()}"
    )
    settings = Gtk.Settings.get_default()
    if settings is None:
        display = Gdk.Display.get_default()
        if display is not None:
            settings = Gtk.Settings.get_for_display(display)
    theme_name = "unknown"
    if settings is not None:
        try:
            theme_name = settings.get_property("gtk-theme-name") or "unknown"
        except TypeError:
            theme_name = getattr(settings.props, "gtk_theme_name", "unknown")
    return version, theme_name


def make_artist_row(
    name: str,
    artist_data: object | None = None,
    image_url: str | None = None,
    app=None,
) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row.add_css_class("artist-row")

    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    content.set_halign(Gtk.Align.FILL)
    content.set_hexpand(True)

    avatar = Gtk.Picture()
    avatar.add_css_class("artist-avatar")
    avatar.set_size_request(32, 32)
    avatar.set_halign(Gtk.Align.START)
    avatar.set_valign(Gtk.Align.CENTER)
    avatar.set_can_shrink(True)
    if hasattr(avatar, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        avatar.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(avatar, "set_keep_aspect_ratio"):
        avatar.set_keep_aspect_ratio(False)

    label = Gtk.Label(label=name, xalign=0)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    label.set_hexpand(True)
    label.set_margin_top(2)
    label.set_margin_bottom(2)
    label.set_valign(Gtk.Align.CENTER)

    content.append(avatar)
    content.append(label)
    row.set_child(content)
    row.artist_data = artist_data if artist_data is not None else name
    row.artist_avatar = avatar

    if image_url and app is not None:
        from ui import image_loader

        image_loader.load_album_art_async(
            avatar,
            image_url,
            32,
            app.auth_token,
            app.image_executor,
            app.get_cache_dir(),
        )

    if app is not None and hasattr(app, "on_artist_row_context_action"):
        popover = Gtk.Popover()
        popover.set_has_arrow(False)
        popover.add_css_class("track-action-popover")
        action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        action_box.set_margin_start(6)
        action_box.set_margin_end(6)
        action_box.set_margin_top(6)
        action_box.set_margin_bottom(6)
        for action in ("View Albums", "Start Radio"):
            action_button = Gtk.Button(label=action)
            action_button.set_halign(Gtk.Align.FILL)
            action_button.set_hexpand(True)
            action_button.add_css_class("track-action-item")
            action_button.connect(
                "clicked",
                app.on_artist_row_context_action,
                popover,
                action,
                row.artist_data,
            )
            action_box.append(action_button)
        popover.set_child(action_box)
        attach_context_popover(row, popover)
        gesture = Gtk.GestureClick.new()
        gesture.set_button(3)

        def on_pressed(_gesture, _n_press: int, x: float, y: float) -> None:
            if hasattr(popover, "set_pointing_to"):
                rect = Gdk.Rectangle()
                rect.x = int(x)
                rect.y = int(y)
                rect.width = 1
                rect.height = 1
                popover.set_pointing_to(rect)
            popover.popup()

        gesture.connect("pressed", on_pressed)
        row.add_controller(gesture)
    return row
