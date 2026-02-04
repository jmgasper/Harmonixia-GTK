import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')

from gi.repository import Gdk, Gtk

from music_assistant_models.enums import AlbumType

from constants import MEDIA_TILE_SIZE
from ui import image_loader, ui_utils
from ui.widgets import album_card, loading_spinner


def build_album_section(app) -> Gtk.Widget:
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.add_css_class("search-section-content")
    content.set_hexpand(True)
    content.set_vexpand(True)

    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    section.add_css_class("search-group")

    header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    header_row.add_css_class("album-header")
    header_row.set_hexpand(True)
    header_row.set_halign(Gtk.Align.FILL)

    header = Gtk.Label(label="Albums")
    header.add_css_class("section-title")
    header.set_xalign(0)
    header.set_hexpand(True)
    app.albums_header = header
    header_row.append(header)

    filter_button = build_album_type_filter_button(app)
    header_row.append(filter_button)

    section.append(header_row)

    status = Gtk.Label(
        label="Configure your Music Assistant server in Settings to load your library."
    )
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    app.library_status_label = status
    section.append(status)

    flow = Gtk.FlowBox()
    ui_utils.configure_media_flowbox(flow, Gtk.SelectionMode.SINGLE)
    flow.connect(
        "child-activated",
        lambda flowbox, child: on_album_activated(app, flowbox, child),
    )
    app.albums_flow = flow
    set_album_items(app, [])
    section.append(flow)

    content.append(section)

    scroller = Gtk.ScrolledWindow()
    scroller.add_css_class("search-section")
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(content)
    scroller.set_vexpand(True)
    app.albums_scroller = scroller

    overlay = Gtk.Overlay()
    overlay.set_child(scroller)

    loading_overlay, spinner, loading_label = (
        loading_spinner.create_loading_overlay()
    )
    overlay.add_overlay(loading_overlay)

    app.library_loading_overlay = loading_overlay
    app.library_loading_spinner = spinner
    app.library_loading_label = loading_label

    return overlay


def build_album_type_filter_button(app) -> Gtk.Widget:
    menu_button = Gtk.MenuButton()
    menu_button.add_css_class("album-filter-button")
    menu_button.set_halign(Gtk.Align.END)

    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    icon_name = pick_icon_name(
        [
            "view-filter-symbolic",
            "nautilus-search-filters-symbolic",
            "filter-photos-symbolic",
            "filter-flagged-symbolic",
            "filter-raw-symbolic",
            "filter-videos-symbolic",
            "system-search-symbolic",
        ]
    )
    filter_icon = Gtk.Image.new_from_icon_name(icon_name)
    filter_icon.set_pixel_size(16)
    content.append(filter_icon)
    content.append(Gtk.Label(label="Filter"))
    menu_button.set_child(content)

    popover = Gtk.Popover()
    popover.set_has_arrow(False)
    popover.add_css_class("album-filter-popover")

    filter_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    filter_box.set_margin_start(6)
    filter_box.set_margin_end(6)
    filter_box.set_margin_top(6)
    filter_box.set_margin_bottom(6)

    app.album_type_check_buttons = {}
    app.selected_album_types = set()
    for album_type in AlbumType:
        label = format_album_type_label(album_type)
        check = Gtk.CheckButton(label=label)
        check.add_css_class("album-filter-item")
        check.set_active(True)
        check.connect(
            "toggled",
            lambda button, album_type_value=album_type.value: (
                on_album_type_filter_toggled(app, button, album_type_value)
            ),
        )
        filter_box.append(check)
        app.album_type_check_buttons[album_type.value] = check
        app.selected_album_types.add(album_type.value)

    popover.set_child(filter_box)
    menu_button.set_popover(popover)
    app.album_type_filter_button = menu_button
    return menu_button


def pick_icon_name(icon_names: list[str]) -> str:
    display = Gdk.Display.get_default()
    if not display:
        return icon_names[-1]
    icon_theme = Gtk.IconTheme.get_for_display(display)
    for icon_name in icon_names:
        if icon_theme.has_icon(icon_name):
            return icon_name
    return icon_names[-1]


def format_album_type_label(album_type: AlbumType) -> str:
    if album_type == AlbumType.EP:
        return "EP"
    return album_type.value.replace("_", " ").title()


def on_album_type_filter_toggled(
    app, button: Gtk.CheckButton, album_type: str
) -> None:
    if button.get_active():
        app.selected_album_types.add(album_type)
    else:
        app.selected_album_types.discard(album_type)
    apply_album_type_filter(app)


def set_album_items(app, albums: list) -> None:
    app.library_albums = albums or []
    apply_album_type_filter(app)
    app.refresh_home_sections()


def apply_album_type_filter(app) -> None:
    selected_types = app.selected_album_types or set()
    if selected_types:
        filtered = [
            album
            for album in app.library_albums
            if app.get_album_type_value(album) in selected_types
        ]
    else:
        filtered = []
    if app.albums_flow:
        populate_album_flow(app, filtered)
    update_album_header_counts(app, len(app.library_albums), len(filtered))


def update_album_header_counts(
    app, total_count: int, filtered_count: int
) -> None:
    if not app.albums_header:
        return
    if total_count and filtered_count != total_count:
        label = f"Albums ({filtered_count} of {total_count})"
    else:
        label = f"Albums ({filtered_count})"
    app.albums_header.set_label(label)


def on_album_activated(
    app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild
) -> None:
    album = getattr(child, "album_data", None)
    if not album:
        return
    app.albums_scroll_position = app.get_albums_scroll_position()
    app.album_detail_previous_view = "albums"
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def populate_album_flow(app, albums: list) -> None:
    if not app.albums_flow:
        return
    visible_view = None
    if app.main_stack:
        try:
            visible_view = app.main_stack.get_visible_child_name()
        except Exception:
            visible_view = None
    load_art = visible_view == "albums" if visible_view is not None else True
    ui_utils.clear_container(app.albums_flow)
    for album in albums:
        image_url = None
        if isinstance(album, dict):
            album_type = app.get_album_type_value(album)
            album_data = dict(album)
            album_data["album_type"] = album_type
            title = album.get("name") or "Unknown Album"
            artist = ui_utils.format_artist_names(album.get("artists") or [])
            image_url = image_loader.extract_album_image_url(album, app.server_url)
        else:
            title, artist = album
            album_data = {
                "name": title,
                "artists": [artist],
                "image_url": image_url,
                "provider_mappings": [],
                "is_sample": True,
                "album_type": AlbumType.ALBUM.value,
            }
        card = album_card.make_album_card(
            app,
            title,
            artist,
            image_url,
            art_size=MEDIA_TILE_SIZE,
            load_art=load_art,
        )
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(MEDIA_TILE_SIZE, -1)
        child.album_data = album_data
        app.albums_flow.append(child)


def ensure_album_grid_artwork(app) -> None:
    flow = app.albums_flow
    if not flow:
        return
    child = flow.get_first_child()
    while child:
        album = getattr(child, "album_data", None)
        card = child.get_child()
        art = card.get_first_child() if card else None
        if isinstance(art, Gtk.Picture) and art.get_paintable() is None:
            image_url = image_loader.extract_album_image_url(
                album,
                app.server_url,
            )
            if image_url:
                image_loader.load_album_art_async(
                    art,
                    image_url,
                    MEDIA_TILE_SIZE,
                    app.auth_token,
                    app.image_executor,
                    app.get_cache_dir(),
                )
        child = child.get_next_sibling()
