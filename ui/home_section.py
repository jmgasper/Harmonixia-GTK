from gi.repository import GLib, Gtk

from constants import HOME_ALBUM_ART_SIZE, HOME_GRID_COLUMNS
from ui import track_table, ui_utils
from ui.widgets import album_card


def build_home_section(app) -> Gtk.Widget:
    home_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    home_box.add_css_class("home-section-content")

    header = Gtk.Label(label="Home")
    header.add_css_class("home-title")
    header.set_xalign(0)
    home_box.append(header)

    played_section, played_list, played_status = build_home_album_list(
        "Recently Played",
        "Play an album to see it here.",
    )
    played_list.album_app = app
    app.home_recently_played_list = played_list
    app.home_recently_played_status = played_status
    home_box.append(played_section)

    recent_tracks_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    recent_tracks_section.add_css_class("search-group")
    recent_tracks_header = Gtk.Label(label="Recently Played Tracks")
    recent_tracks_header.add_css_class("section-title")
    recent_tracks_header.set_xalign(0)
    recent_tracks_section.append(recent_tracks_header)
    recent_tracks_table = track_table.build_tracks_table(
        app,
        store_attr="home_recent_tracks_store",
        sort_model_attr="home_recent_tracks_sort_model",
        selection_attr="home_recent_tracks_selection",
        view_attr="home_recent_tracks_view",
        use_track_art=True,
        include_album_column=True,
    )
    recent_tracks_scroller = Gtk.ScrolledWindow()
    recent_tracks_scroller.set_policy(
        Gtk.PolicyType.AUTOMATIC,
        Gtk.PolicyType.AUTOMATIC,
    )
    recent_tracks_scroller.set_child(recent_tracks_table)
    if hasattr(recent_tracks_scroller, "set_propagate_natural_height"):
        recent_tracks_scroller.set_propagate_natural_height(True)
    recent_tracks_scroller.set_vexpand(False)
    recent_tracks_section.append(recent_tracks_scroller)

    recent_tracks_status = Gtk.Label(label="Play tracks to see them here.")
    recent_tracks_status.add_css_class("status-label")
    recent_tracks_status.set_xalign(0)
    recent_tracks_status.set_wrap(True)
    recent_tracks_status.set_visible(False)
    recent_tracks_status.empty_message = "Play tracks to see them here."
    recent_tracks_section.append(recent_tracks_status)
    app.home_recent_tracks_status = recent_tracks_status
    home_box.append(recent_tracks_section)

    added_section, added_list, added_status = build_home_album_list(
        "Recently Added Albums",
        "Recently added albums will appear here.",
    )
    added_list.album_app = app
    app.home_recently_added_list = added_list
    app.home_recently_added_status = added_status
    home_box.append(added_section)

    (
        recommendations_container,
        recommendations_box,
        recommendations_status,
    ) = build_home_recommendations_container()
    app.home_recommendations_box = recommendations_box
    app.home_recommendations_status = recommendations_status
    home_box.append(recommendations_container)

    scroller = Gtk.ScrolledWindow()
    scroller.add_css_class("home-section")
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(home_box)
    scroller.set_vexpand(True)

    last_width = {"value": 0}

    def on_home_tick(widget, _frame_clock) -> bool:
        width = widget.get_allocated_width()
        if width != last_width["value"]:
            last_width["value"] = width
            _apply_home_layout(app, width)
        return GLib.SOURCE_CONTINUE

    scroller.add_tick_callback(on_home_tick)

    app.refresh_home_sections()
    return scroller


def build_home_recommendations_container() -> tuple[Gtk.Widget, Gtk.Box, Gtk.Label]:
    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

    status = Gtk.Label(label="Recommendations will appear here.")
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    status.empty_message = "Recommendations will appear here."
    container.append(status)

    sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    container.append(sections)
    return container, sections, status


def build_home_album_list(
    title: str, empty_message: str
) -> tuple[Gtk.Widget, Gtk.FlowBox, Gtk.Label]:
    return build_home_media_list(title, empty_message, on_home_album_activated)


def build_home_recommendation_list(
    title: str, empty_message: str
) -> tuple[Gtk.Widget, Gtk.FlowBox, Gtk.Label]:
    return build_home_media_list(
        title,
        empty_message,
        on_home_recommendation_activated,
    )


def build_home_media_list(
    title: str,
    empty_message: str,
    on_activate,
) -> tuple[Gtk.Widget, Gtk.FlowBox, Gtk.Label]:
    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    section.add_css_class("search-group")

    header = Gtk.Label(label=title)
    header.add_css_class("section-title")
    header.set_xalign(0)
    section.append(header)

    flow = Gtk.FlowBox()
    ui_utils.configure_media_flowbox(
        flow,
        Gtk.SelectionMode.NONE,
        homogeneous=True,
        css_class="home-grid",
        min_children_per_line=3,
        max_children_per_line=5,
    )
    flow.home_art_size = HOME_ALBUM_ART_SIZE
    if on_activate:
        flow.connect(
            "child-activated",
            lambda flowbox, child: on_activate(
                getattr(flowbox, "album_app", None),
                flowbox,
                child,
            ),
        )
    section.append(flow)

    status = Gtk.Label(label=empty_message)
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    status.empty_message = empty_message
    section.append(status)

    return section, flow, status


def _apply_home_layout(app, width: int) -> None:
    if width <= 0:
        return
    if width < 700:
        columns = 3
    elif width < 1000:
        columns = 4
    else:
        columns = 5
    flows = [
        getattr(app, "home_recently_played_list", None),
        getattr(app, "home_recently_added_list", None),
    ]
    flows.extend(getattr(app, "home_recommendation_flows", []) or [])
    for flow in flows:
        if flow is None:
            continue
        flow.set_min_children_per_line(columns)
        flow.set_max_children_per_line(columns)


def _trim_items_to_full_rows(items: list, columns: int) -> list:
    if columns <= 0:
        return items
    total = len(items)
    if total < columns:
        return items
    remainder = total % columns
    if remainder == 0:
        return items
    return items[: total - remainder]


def on_home_album_activated(app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
    if not app:
        return
    album = getattr(child, "album_data", None)
    if not album:
        return
    app.album_detail_previous_view = "home"
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def populate_home_album_list(
    app,
    listbox: Gtk.FlowBox | None,
    albums: list,
    art_size: int | None = None,
) -> None:
    if not listbox:
        return
    if art_size is None:
        art_size = getattr(listbox, "home_art_size", HOME_ALBUM_ART_SIZE)
    valid_albums = [album for album in albums if isinstance(album, dict)]
    columns = listbox.get_max_children_per_line() or HOME_GRID_COLUMNS
    valid_albums = _trim_items_to_full_rows(valid_albums, columns)
    ui_utils.clear_container(listbox)
    for album in valid_albums:
        card = album_card.make_home_album_card(app, album, art_size=art_size)
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(art_size, -1)
        child.album_data = album
        listbox.append(child)


def populate_home_recommendations(app, sections: list) -> None:
    if not app.home_recommendations_box:
        return
    ui_utils.clear_container(app.home_recommendations_box)
    app.home_recommendation_flows = []
    visible_sections: list[dict] = []
    for section_data in sections:
        if not isinstance(section_data, dict):
            continue
        title = section_data.get("title") or "Recommendations"
        items = section_data.get("items") or []
        if not isinstance(items, list):
            continue
        valid_items = [item for item in items if isinstance(item, dict)]
        if not valid_items:
            continue
        empty_message = section_data.get(
            "empty_message",
            "No recommendations available.",
        )
        section, flow, status = build_home_recommendation_list(
            title, empty_message
        )
        flow.album_app = app
        app.home_recommendation_flows.append(flow)
        app.home_recommendations_box.append(section)
        populate_home_recommendation_list(app, flow, valid_items)
        update_home_status(status, valid_items)
        visible_sections.append(section_data)
    if app.home_recommendations_status:
        update_home_status(app.home_recommendations_status, visible_sections)


def populate_home_recommendation_list(
    app,
    listbox: Gtk.FlowBox | None,
    items: list,
    art_size: int | None = None,
) -> None:
    if not listbox:
        return
    if art_size is None:
        art_size = getattr(listbox, "home_art_size", HOME_ALBUM_ART_SIZE)
    valid_items = [item for item in items if isinstance(item, dict)]
    columns = listbox.get_max_children_per_line() or HOME_GRID_COLUMNS
    valid_items = _trim_items_to_full_rows(valid_items, columns)
    ui_utils.clear_container(listbox)
    for item in valid_items:
        card = _make_recommendation_card(app, item, art_size)
        if not card:
            continue
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(art_size, -1)
        child.recommendation_item = item
        listbox.append(child)


def _make_recommendation_card(
    app,
    item: dict,
    art_size: int,
) -> Gtk.Widget | None:
    title = item.get("title") or "Unknown"
    subtitle = item.get("subtitle") or ""
    image_url = item.get("image_url")
    media_type = item.get("media_type")
    if media_type == "playlist":
        return album_card.make_playlist_card(
            app,
            title,
            image_url,
            art_size=art_size,
        )
    provider_domain = None
    payload = item.get("payload")
    if isinstance(payload, dict):
        provider_domain = album_card.get_album_provider_domain(payload)
    show_artist = bool(subtitle)
    return album_card.make_album_card(
        app,
        title,
        subtitle,
        image_url,
        art_size=art_size,
        show_artist=show_artist,
        provider_domain=provider_domain,
        album_data=payload if isinstance(payload, dict) else item,
    )


def on_home_recommendation_activated(
    app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild
) -> None:
    if not app:
        return
    item = getattr(child, "recommendation_item", None)
    if not isinstance(item, dict):
        return
    media_type = item.get("media_type")
    payload = item.get("payload")
    if media_type == "album" and isinstance(payload, dict):
        app.album_detail_previous_view = "home"
        app.show_album_detail(payload)
        if app.main_stack:
            app.main_stack.set_visible_child_name("album-detail")
    elif media_type == "playlist" and isinstance(payload, dict):
        if not app.main_stack:
            return
        app.show_playlist_detail(payload)
        app.main_stack.set_visible_child_name("playlist-detail")
        if app.home_nav_list:
            app.home_nav_list.unselect_all()
        if app.library_list:
            app.library_list.unselect_all()
        if app.playlists_list:
            app.playlists_list.unselect_all()
    elif media_type == "artist" and payload:
        app.show_artist_albums(payload, "home")


def set_home_status(label: Gtk.Label | None, message: str) -> None:
    if not label:
        return
    label.set_label(message)
    label.set_visible(bool(message))


def update_home_status(label: Gtk.Label | None, albums: list) -> None:
    if not label:
        return
    empty_message = getattr(label, "empty_message", "")
    label.set_label(empty_message if not albums else "")
    label.set_visible(not albums and bool(empty_message))
