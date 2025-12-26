from gi.repository import Gtk

from ui import track_table, ui_utils


def build_search_section(app) -> Gtk.Widget:
    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    container.add_css_class("search-section-content")
    container.set_hexpand(True)
    container.set_vexpand(True)

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
