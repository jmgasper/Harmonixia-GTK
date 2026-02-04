from gi.repository import Gtk, GLib

from ui import track_table, ui_utils


COMPACT_MAX_WIDTH = 600
ROOMY_MIN_WIDTH = 900


def _set_css_class(widget: Gtk.Widget | None, css_class: str, enabled: bool) -> None:
    if widget is None:
        return
    if enabled:
        widget.add_css_class(css_class)
    else:
        widget.remove_css_class(css_class)


def _apply_search_layout(app, width: int) -> None:
    if width <= 0:
        return
    if width < COMPACT_MAX_WIDTH:
        layout = "compact"
    elif width >= ROOMY_MIN_WIDTH:
        layout = "roomy"
    else:
        layout = "medium"
    if getattr(app, "search_layout_mode", None) == layout:
        return
    app.search_layout_mode = layout

    container = getattr(app, "search_section_container", None)
    _set_css_class(container, "search-layout-compact", layout == "compact")
    _set_css_class(container, "search-layout-roomy", layout == "roomy")

    if layout == "compact":
        min_children = 1
        max_children = 2
        spacing = 8
    elif layout == "roomy":
        min_children = 3
        max_children = 6
        spacing = 16
    else:
        min_children = 2
        max_children = 4
        spacing = 12

    for flow in (
        getattr(app, "search_playlists_flow", None),
        getattr(app, "search_albums_flow", None),
    ):
        if flow is None:
            continue
        flow.set_min_children_per_line(min_children)
        flow.set_max_children_per_line(max_children)
        flow.set_row_spacing(spacing)
        flow.set_column_spacing(spacing)
        _set_css_class(flow, "search-grid-compact", layout == "compact")
        _set_css_class(flow, "search-grid-roomy", layout == "roomy")

    artists_list = getattr(app, "search_artists_list", None)
    if artists_list is not None:
        _set_css_class(artists_list, "search-layout-compact", layout == "compact")
        _set_css_class(artists_list, "search-layout-roomy", layout == "roomy")
        if layout == "compact":
            list_margin = 4
        elif layout == "roomy":
            list_margin = 10
        else:
            list_margin = 6
        artists_list.set_margin_top(list_margin)
        artists_list.set_margin_bottom(list_margin)

    tracks_scroller = getattr(app, "search_tracks_scroller", None)
    if tracks_scroller is not None:
        _set_css_class(
            tracks_scroller, "search-layout-compact", layout == "compact"
        )
        _set_css_class(tracks_scroller, "search-layout-roomy", layout == "roomy")
        if layout == "compact":
            min_rows = 8
            scroller_margin = 4
        elif layout == "roomy":
            min_rows = 14
            scroller_margin = 10
        else:
            min_rows = 11
            scroller_margin = 6
        row_height = 32
        min_height = min_rows * row_height + 40
        if hasattr(tracks_scroller, "set_min_content_height"):
            tracks_scroller.set_min_content_height(min_height)
        else:
            tracks_scroller.set_size_request(-1, min_height)
        tracks_scroller.set_margin_top(scroller_margin)
        tracks_scroller.set_margin_bottom(scroller_margin)


def build_search_section(app) -> Gtk.Widget:
    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    container.add_css_class("search-section-content")
    container.set_hexpand(True)
    container.set_vexpand(True)
    app.search_section_container = container

    scope_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    scope_box.add_css_class("search-group")
    scope_box.set_hexpand(True)
    scope_box.set_halign(Gtk.Align.FILL)
    scope_toggle = Gtk.CheckButton(label="Search library only")
    scope_toggle.add_css_class("search-scope-toggle")
    scope_toggle.set_active(bool(getattr(app, "search_library_only", True)))
    scope_toggle.connect("toggled", app.on_search_scope_toggled)
    scope_box.append(scope_toggle)
    container.append(scope_box)
    app.search_scope_toggle = scope_toggle

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    container.append(status)
    app.search_status_label = status

    playlists_section, playlists_flow = build_flow_section("Playlists")
    playlists_flow.connect("child-activated", app.on_search_playlist_activated)
    app.search_playlists_section = playlists_section
    app.search_playlists_flow = playlists_flow
    container.append(playlists_section)

    albums_section, albums_flow = build_flow_section("Albums")
    albums_flow.connect("child-activated", app.on_search_album_activated)
    app.search_albums_section = albums_section
    app.search_albums_flow = albums_flow
    container.append(albums_section)

    artists_section, artists_list = build_artists_section()
    artists_list.set_activate_on_single_click(True)
    artists_list.connect("row-activated", app.on_artist_row_activated)
    app.search_artists_section = artists_section
    app.search_artists_list = artists_list
    container.append(artists_section)

    tracks_section, tracks_scroller = build_tracks_section(app)
    app.search_tracks_section = tracks_section
    app.search_tracks_scroller = tracks_scroller
    container.append(tracks_section)

    scroller = Gtk.ScrolledWindow()
    scroller.add_css_class("search-section")
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(container)
    scroller.set_vexpand(True)

    last_width = {"value": 0}

    def on_search_tick(widget, _frame_clock) -> bool:
        width = widget.get_allocated_width()
        if width != last_width["value"]:
            last_width["value"] = width
            _apply_search_layout(app, width)
        return GLib.SOURCE_CONTINUE

    scroller.add_tick_callback(on_search_tick)

    app.search_results_view = scroller
    return scroller


def build_flow_section(title: str) -> tuple[Gtk.Box, Gtk.FlowBox]:
    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    section.add_css_class("search-group")

    header = Gtk.Label(label=title)
    header.add_css_class("section-title")
    header.set_xalign(0)
    section.append(header)

    flow = Gtk.FlowBox()
    ui_utils.configure_media_flowbox(flow, Gtk.SelectionMode.SINGLE)
    section.append(flow)

    section.set_visible(False)
    return section, flow


def build_artists_section() -> tuple[Gtk.Box, Gtk.ListBox]:
    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    section.add_css_class("search-group")

    header = Gtk.Label(label="Artists")
    header.add_css_class("section-title")
    header.set_xalign(0)
    section.append(header)

    artists_list = Gtk.ListBox()
    artists_list.add_css_class("artist-list")
    artists_list.add_css_class("search-artist-list")
    artists_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    artists_list.set_show_separators(True)
    section.append(artists_list)

    section.set_visible(False)
    return section, artists_list


def build_tracks_section(app) -> tuple[Gtk.Box, Gtk.ScrolledWindow]:
    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    section.add_css_class("search-group")

    header = Gtk.Label(label="Tracks")
    header.add_css_class("section-title")
    header.set_xalign(0)
    section.append(header)

    tracks_table = track_table.build_tracks_table(
        app,
        store_attr="search_tracks_store",
        sort_model_attr="search_tracks_sort_model",
        selection_attr="search_tracks_selection",
        view_attr="search_tracks_view",
    )
    tracks_scroller = Gtk.ScrolledWindow()
    tracks_scroller.add_css_class("search-tracks-scroller")
    tracks_scroller.set_policy(
        Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
    )
    tracks_scroller.set_child(tracks_table)
    min_rows = 12
    row_height = 32
    min_height = min_rows * row_height + 40
    if hasattr(tracks_scroller, "set_propagate_natural_height"):
        tracks_scroller.set_propagate_natural_height(False)
    if hasattr(tracks_scroller, "set_min_content_height"):
        tracks_scroller.set_min_content_height(min_height)
    else:
        tracks_scroller.set_size_request(-1, min_height)
    tracks_scroller.set_vexpand(False)
    section.append(tracks_scroller)

    section.set_visible(False)
    return section, tracks_scroller
