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
        container.remove(child)
        child = container.get_first_child()


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


def make_artist_row(name: str, artist_data: object | None = None) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row.add_css_class("artist-row")

    label = Gtk.Label(label=name, xalign=0)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    label.set_margin_top(2)
    label.set_margin_bottom(2)
    row.set_child(label)
    row.artist_data = artist_data if artist_data is not None else name
    return row
