import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')

from gi.repository import Gdk, GLib, Gtk

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
ALBUM_ART_SCROLL_DEBOUNCE_MS = 40
ALBUM_ART_BACKGROUND_DELAY_MS = 180
ALBUM_ART_VISIBLE_ROWS = 3
ALBUM_ART_PRELOAD_ROWS = 2
ALBUM_ART_MIN_VISIBLE_BATCH = 12
ALBUM_ART_MIN_BACKGROUND_BATCH = 4
SHOW_ALBUM_PROVIDER_FILTERS = False


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
    if SHOW_ALBUM_PROVIDER_FILTERS:
        section.append(build_provider_filter_bar(app))
    else:
        app.album_provider_filter_bar = None
        app.provider_check_buttons.clear()

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
    _connect_album_artwork_scroll_handlers(app)

    overlay = Gtk.Overlay()
    overlay.set_child(scroller)

    loading_overlay, spinner, loading_label, progress_bar, sub_label = (
        loading_spinner.create_loading_overlay()
    )
    overlay.add_overlay(loading_overlay)

    app.library_loading_overlay = loading_overlay
    app.library_loading_spinner = spinner
    app.library_loading_label = loading_label
    app.library_loading_progress_bar = progress_bar
    app.library_loading_sub_label = sub_label

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


def build_provider_filter_bar(app) -> Gtk.Widget:
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    bar.add_css_class("provider-filter-bar")
    app.album_provider_filter_bar = bar
    _rebuild_provider_chips(app, bar, app.provider_check_buttons)
    return bar


def _provider_display_name(provider_domain: str) -> str:
    if provider_domain == "filesystem":
        return "Local"
    if provider_domain == "tidal":
        return "TIDAL"
    return provider_domain.title()


def _normalize_provider_domain(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().casefold()
    return text or None


def _read_provider_value(item: object, key: str) -> object:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _provider_domains_from_instances(instances: object) -> set[str]:
    domains: set[str] = set()
    if isinstance(instances, dict):
        values = instances.values()
    elif isinstance(instances, (list, tuple, set)):
        values = instances
    else:
        values = []
    for instance in values:
        domain = (
            _read_provider_value(instance, "domain")
            or _read_provider_value(instance, "provider_domain")
            or _read_provider_value(instance, "provider")
        )
        normalized = _normalize_provider_domain(domain)
        if normalized:
            domains.add(normalized)
    return domains


def _resolve_provider_domains(
    app,
    discovered_domains: set[str] | None = None,
) -> list[str]:
    resolved: set[str] = set()
    manifests = getattr(app, "provider_manifests", None) or {}
    if isinstance(manifests, dict):
        for domain in manifests.keys():
            normalized = _normalize_provider_domain(domain)
            if normalized:
                resolved.add(normalized)
    elif isinstance(manifests, (list, tuple, set)):
        for manifest in manifests:
            normalized = _normalize_provider_domain(
                _read_provider_value(manifest, "domain")
            )
            if normalized:
                resolved.add(normalized)

    if not resolved:
        resolved = _provider_domains_from_instances(
            getattr(app, "provider_instances", None)
        )

    if not resolved:
        for domain in discovered_domains or set():
            normalized = _normalize_provider_domain(domain)
            if normalized:
                resolved.add(normalized)

    return sorted(resolved)


def _rebuild_provider_chips(app, bar, check_buttons_dict) -> None:
    if bar is None:
        return
    previous_providers = set(check_buttons_dict.keys())
    selected_providers = getattr(app, "selected_providers", None)
    if isinstance(selected_providers, set):
        prior_selection = set(selected_providers)
    else:
        prior_selection = set(selected_providers or [])
        selected_providers = prior_selection
        app.selected_providers = selected_providers

    child = bar.get_first_child()
    while child:
        next_child = child.get_next_sibling()
        bar.remove(child)
        child = next_child
    check_buttons_dict.clear()

    discovered_providers = set()
    for album in app.library_albums or []:
        provider_domain = _pick_album_provider_domain(album)
        if provider_domain:
            discovered_providers.add(provider_domain)

    ordered_providers = _resolve_provider_domains(app, discovered_providers)
    available_providers = set(ordered_providers)
    if prior_selection:
        selected_providers.intersection_update(available_providers)
    elif not previous_providers:
        selected_providers.clear()
        selected_providers.update(ordered_providers)
    else:
        selected_providers.clear()

    for provider_domain in ordered_providers:
        button = Gtk.ToggleButton(label=_provider_display_name(provider_domain))
        button.add_css_class("provider-filter-chip")
        button.set_active(provider_domain in selected_providers)
        button.connect(
            "toggled",
            lambda toggle_button, domain=provider_domain: (
                on_provider_filter_toggled(app, toggle_button, domain)
            ),
        )
        bar.append(button)
        check_buttons_dict[provider_domain] = button

    bar.set_visible(bool(ordered_providers))


def on_provider_filter_toggled(
    app, button: Gtk.ToggleButton, provider_domain: str
) -> None:
    if button.get_active():
        app.selected_providers.add(provider_domain)
    else:
        app.selected_providers.discard(provider_domain)
    apply_album_type_filter(app)


def refresh_provider_filter_bar(app) -> None:
    if not SHOW_ALBUM_PROVIDER_FILTERS:
        return
    if app.album_provider_filter_bar is None:
        return
    _rebuild_provider_chips(
        app,
        app.album_provider_filter_bar,
        app.provider_check_buttons,
    )


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
    if hasattr(app, "persist_album_density"):
        app.persist_album_density()
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
    refresh_provider_filter_bar(app)
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
    should_filter_by_provider = (
        SHOW_ALBUM_PROVIDER_FILTERS and app.album_provider_filter_bar is not None
    )
    selected_providers = set(app.selected_providers or set())
    if should_filter_by_provider and selected_providers:
        filtered = [
            album
            for album in filtered
            if _pick_album_provider_domain(album) in selected_providers
        ]
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
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")
    app.show_album_detail(album)


def populate_album_flow(app, albums: list) -> None:
    if not app.albums_flow:
        return
    _cancel_album_artwork_schedules(app)
    tile_size = getattr(app, "album_tile_size", MEDIA_TILE_SIZE)
    visible_view = None
    if app.main_stack:
        try:
            visible_view = app.main_stack.get_visible_child_name()
        except Exception:
            visible_view = None
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
            load_art=False,
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
        child.album_image_url = image_url
        app.albums_flow.append(child)
    if visible_view == "albums":
        schedule_album_grid_artwork_refresh(app, immediate=True)


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


def _get_card_art_picture(card: Gtk.Widget | None) -> Gtk.Picture | None:
    if card is None:
        return None
    first_child = card.get_first_child()
    if isinstance(first_child, Gtk.Picture):
        return first_child
    if isinstance(first_child, Gtk.Overlay):
        overlay_child = first_child.get_child()
        if isinstance(overlay_child, Gtk.Picture):
            return overlay_child
    return None


def _connect_album_artwork_scroll_handlers(app) -> None:
    scroller = getattr(app, "albums_scroller", None)
    if not isinstance(scroller, Gtk.ScrolledWindow):
        return
    if getattr(app, "_album_artwork_handlers_connected", False):
        return
    adjustment = scroller.get_vadjustment()
    if adjustment is not None:
        adjustment.connect(
            "value-changed",
            lambda _adj: schedule_album_grid_artwork_refresh(app),
        )
        adjustment.connect(
            "changed",
            lambda _adj: schedule_album_grid_artwork_refresh(app),
        )
    scroller.connect(
        "map",
        lambda *_args: schedule_album_grid_artwork_refresh(app, immediate=True),
    )
    app._album_artwork_handlers_connected = True


def _cancel_album_artwork_schedules(app) -> None:
    refresh_id = getattr(app, "_album_artwork_refresh_id", None)
    if refresh_id:
        GLib.source_remove(refresh_id)
        app._album_artwork_refresh_id = None
    background_id = getattr(app, "_album_artwork_background_id", None)
    if background_id:
        GLib.source_remove(background_id)
        app._album_artwork_background_id = None


def schedule_album_grid_artwork_refresh(
    app, immediate: bool = False
) -> None:
    refresh_id = getattr(app, "_album_artwork_refresh_id", None)
    if refresh_id:
        GLib.source_remove(refresh_id)
    if immediate:
        app._album_artwork_refresh_id = GLib.idle_add(
            _run_album_grid_artwork_refresh,
            app,
        )
    else:
        app._album_artwork_refresh_id = GLib.timeout_add(
            ALBUM_ART_SCROLL_DEBOUNCE_MS,
            _run_album_grid_artwork_refresh,
            app,
        )


def _run_album_grid_artwork_refresh(app) -> bool:
    app._album_artwork_refresh_id = None
    ensure_album_grid_artwork(app)
    return False


def _schedule_album_grid_background_refresh(app) -> None:
    if getattr(app, "_album_artwork_background_id", None):
        return
    app._album_artwork_background_id = GLib.timeout_add(
        ALBUM_ART_BACKGROUND_DELAY_MS,
        _run_album_grid_background_refresh,
        app,
    )


def _run_album_grid_background_refresh(app) -> bool:
    app._album_artwork_background_id = None
    ensure_album_grid_artwork(app)
    return False


def _is_child_near_viewport(
    child: Gtk.FlowBoxChild,
    top: float,
    bottom: float,
    fallback_height: int,
) -> bool:
    try:
        allocation = child.get_allocation()
    except Exception:
        return True
    child_top = float(getattr(allocation, "y", 0))
    child_height = float(getattr(allocation, "height", 0))
    if child_height <= 0:
        child_height = float(child.get_allocated_height() or fallback_height)
    child_bottom = child_top + child_height
    return child_bottom >= top and child_top <= bottom


def _load_album_art_batch(app, targets, tile_size: int, limit: int) -> int:
    loaded = 0
    for art, image_url in targets:
        if loaded >= limit:
            break
        expected_url = getattr(art, "expected_image_url", None)
        if expected_url and expected_url == image_url:
            continue
        image_loader.load_album_art_async(
            art,
            image_url,
            tile_size,
            app.auth_token,
            app.image_executor,
            app.get_cache_dir(),
        )
        loaded += 1
    return loaded


def ensure_album_grid_artwork(app) -> None:
    if app.main_stack:
        try:
            if app.main_stack.get_visible_child_name() != "albums":
                _cancel_album_artwork_schedules(app)
                return
        except Exception:
            pass
    flow = app.albums_flow
    if not flow:
        return
    tile_size = getattr(app, "album_tile_size", MEDIA_TILE_SIZE)
    columns = max(1, flow.get_max_children_per_line() or 1)
    visible_limit = max(
        ALBUM_ART_MIN_VISIBLE_BATCH,
        columns * ALBUM_ART_VISIBLE_ROWS,
    )
    background_limit = max(ALBUM_ART_MIN_BACKGROUND_BATCH, columns)
    preload_pixels = (
        tile_size + max(0, flow.get_row_spacing())
    ) * ALBUM_ART_PRELOAD_ROWS
    view_top = None
    view_bottom = None
    scroller = getattr(app, "albums_scroller", None)
    if isinstance(scroller, Gtk.ScrolledWindow):
        adjustment = scroller.get_vadjustment()
        if adjustment is not None:
            value = float(adjustment.get_value())
            page_size = float(adjustment.get_page_size())
            view_top = max(0.0, value - preload_pixels)
            view_bottom = value + page_size + preload_pixels

    visible_targets = []
    deferred_targets = []
    child = flow.get_first_child()
    while child:
        album = getattr(child, "album_data", None)
        card = child.get_child()
        art = _get_card_art_picture(card)
        if not isinstance(art, Gtk.Picture) or art.get_paintable() is not None:
            child = child.get_next_sibling()
            continue
        image_url = getattr(child, "album_image_url", None)
        if not image_url:
            image_url = image_loader.extract_album_image_url(
                album,
                app.server_url,
            )
            child.album_image_url = image_url
        if not image_url:
            child = child.get_next_sibling()
            continue
        if view_top is None or view_bottom is None or _is_child_near_viewport(
            child,
            view_top,
            view_bottom,
            tile_size,
        ):
            visible_targets.append((art, image_url))
        else:
            deferred_targets.append((art, image_url))
        child = child.get_next_sibling()

    loaded = _load_album_art_batch(
        app,
        visible_targets,
        tile_size,
        visible_limit,
    )
    loaded += _load_album_art_batch(
        app,
        deferred_targets,
        tile_size,
        background_limit,
    )
    remaining = len(visible_targets) + len(deferred_targets) - loaded
    if remaining > 0:
        _schedule_album_grid_background_refresh(app)
