import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')

from gi.repository import Gdk, Gtk

from music_assistant_models.enums import AlbumType

from constants import (
    MEDIA_TILE_SIZE,
    MEDIA_TILE_SIZE_COMPACT,
    MEDIA_TILE_SIZE_LARGE,
    MEDIA_TILE_SIZE_NORMAL,
)
from ui import image_loader, ui_utils
from ui.widgets import album_card, loading_spinner

FAVORITES_FILTER_VALUE = "favorites"


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

    if not getattr(app, "album_tile_size", None):
        app.album_tile_size = MEDIA_TILE_SIZE_NORMAL

    if not getattr(app, "album_sort_order", None):
        app.album_sort_order = "sort_name"

    density_controls = build_album_density_controls(app)
    sort_button = build_album_sort_button(app)
    filter_button = build_album_type_filter_button(app)
    refresh_button = Gtk.Button()
    refresh_button.add_css_class("flat")
    refresh_button.set_tooltip_text("Refresh library")
    refresh_button.set_child(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
    refresh_button.connect("clicked", lambda _button: app.load_library())
    refresh_button.set_sensitive(not bool(getattr(app, "library_loading", False)))
    app.albums_refresh_button = refresh_button

    header_row.append(density_controls)
    header_row.append(sort_button)
    header_row.append(filter_button)
    header_row.append(refresh_button)

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


def build_album_density_controls(app) -> Gtk.Widget:
    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
    controls.add_css_class("album-density-controls")
    current_size = getattr(app, "album_tile_size", MEDIA_TILE_SIZE_NORMAL)
    if current_size not in (
        MEDIA_TILE_SIZE_COMPACT,
        MEDIA_TILE_SIZE_NORMAL,
        MEDIA_TILE_SIZE_LARGE,
    ):
        current_size = MEDIA_TILE_SIZE_NORMAL
        app.album_tile_size = current_size

    app.album_density_buttons = {}
    first_button: Gtk.ToggleButton | None = None
    for label, tile_size in (
        ("S", MEDIA_TILE_SIZE_COMPACT),
        ("M", MEDIA_TILE_SIZE_NORMAL),
        ("L", MEDIA_TILE_SIZE_LARGE),
    ):
        button = Gtk.ToggleButton(label=label)
        button.add_css_class("album-filter-button")
        button.add_css_class("album-density-button")
        if first_button is None:
            first_button = button
        else:
            button.set_group(first_button)
        button.set_active(tile_size == current_size)
        button.connect(
            "toggled",
            lambda toggle, value=tile_size: on_album_density_toggled(
                app,
                toggle,
                value,
            ),
        )
        controls.append(button)
        app.album_density_buttons[tile_size] = button
    return controls


def on_album_density_toggled(
    app,
    button: Gtk.ToggleButton,
    tile_size: int,
) -> None:
    if not button.get_active():
        return
    if getattr(app, "album_tile_size", MEDIA_TILE_SIZE_NORMAL) == tile_size:
        return
    app.album_tile_size = tile_size
    if hasattr(app, "persist_album_density"):
        app.persist_album_density()
    apply_album_type_filter(app)


def build_album_sort_button(app) -> Gtk.Widget:
    menu_button = Gtk.MenuButton(label="Sort")
    menu_button.add_css_class("album-filter-button")
    menu_button.add_css_class("album-sort-button")
    menu_button.set_halign(Gtk.Align.END)

    popover = Gtk.Popover()
    popover.set_has_arrow(False)
    popover.add_css_class("album-filter-popover")

    sort_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    sort_box.set_margin_start(6)
    sort_box.set_margin_end(6)
    sort_box.set_margin_top(6)
    sort_box.set_margin_bottom(6)

    options = (
        ("Name", "sort_name"),
        ("Artist", "sort_artist"),
        ("Year", "year_desc"),
        ("Date Added", "timestamp_added_desc"),
    )
    current_order = getattr(app, "album_sort_order", None) or "sort_name"
    app.album_sort_order = current_order
    app.album_sort_buttons = {}
    first_check: Gtk.CheckButton | None = None
    for label, order_value in options:
        check = Gtk.CheckButton(label=label)
        check.add_css_class("album-filter-item")
        if first_check is None:
            first_check = check
        else:
            check.set_group(first_check)
        check.set_active(order_value == current_order)
        check.connect(
            "toggled",
            lambda button, value=order_value: on_album_sort_toggled(
                app,
                button,
                value,
            ),
        )
        sort_box.append(check)
        app.album_sort_buttons[order_value] = check

    popover.set_child(sort_box)
    menu_button.set_popover(popover)
    app.album_sort_button = menu_button
    return menu_button


def on_album_sort_toggled(
    app,
    button: Gtk.CheckButton,
    order_value: str,
) -> None:
    if not button.get_active():
        return
    if getattr(app, "album_sort_order", None) == order_value:
        return
    app.album_sort_order = order_value
    app.load_library()


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
    selected_types = set(app.selected_album_types or set())
    favorite_only = FAVORITES_FILTER_VALUE in selected_types
    if getattr(app, "album_filter_favorite_only", False) != favorite_only:
        app.album_filter_favorite_only = favorite_only
        if app.server_url and not app.library_loading:
            app.load_library()
            return
    selected_types.discard(FAVORITES_FILTER_VALUE)
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
    tile_size = getattr(app, "album_tile_size", MEDIA_TILE_SIZE)
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
            art_size=tile_size,
            load_art=load_art,
            provider_domain=_pick_album_provider_domain(album_data),
            album_data=album_data,
        )
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(tile_size, -1)
        child.album_data = album_data
        app.albums_flow.append(child)


def _pick_album_provider_domain(album: object) -> str | None:
    mappings = []
    if isinstance(album, dict):
        mappings = album.get("provider_mappings") or []
    else:
        mappings = getattr(album, "provider_mappings", None) or []
    domains: list[str] = []
    for mapping in mappings:
        if isinstance(mapping, dict):
            domain = mapping.get("provider_domain") or mapping.get(
                "provider_instance"
            )
        else:
            domain = getattr(mapping, "provider_domain", None) or getattr(
                mapping, "provider_instance", None
            )
        if not domain:
            continue
        domain_text = str(domain).strip().casefold()
        if domain_text:
            domains.append(domain_text)
    if not domains:
        return None
    if "tidal" in domains:
        return "tidal"
    if "filesystem" in domains:
        return "filesystem"
    return domains[0]


def ensure_album_grid_artwork(app) -> None:
    flow = app.albums_flow
    if not flow:
        return
    tile_size = getattr(app, "album_tile_size", MEDIA_TILE_SIZE)
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
                    tile_size,
                    app.auth_token,
                    app.image_executor,
                    app.get_cache_dir(),
                )
        child = child.get_next_sibling()
