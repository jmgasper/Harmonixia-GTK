from gi.repository import Gdk, Gtk, Pango

from constants import HOME_ALBUM_ART_SIZE, MEDIA_TILE_SIZE
from ui import image_loader, ui_utils


def make_album_card(
    app,
    title: str,
    artist: str,
    image_url: str | None = None,
    art_size: int = MEDIA_TILE_SIZE,
    card_class: str | None = None,
    show_artist: bool = True,
    load_art: bool = True,
    provider_domain: str | None = None,
    album_data: object | None = None,
    enable_album_actions: bool = True,
) -> Gtk.Widget:
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("album-card")
    if card_class:
        card.add_css_class(card_class)
    card.set_size_request(art_size, -1)
    card.set_halign(Gtk.Align.CENTER)
    card.set_valign(Gtk.Align.START)
    card.set_hexpand(False)
    card.set_vexpand(False)

    card.album_data = (
        album_data
        if album_data is not None
        else {
            "name": title,
            "artists": [artist] if artist else [],
            "image_url": image_url,
        }
    )

    art = Gtk.Picture()
    art.add_css_class("album-art")
    art.set_size_request(art_size, art_size)
    art.set_halign(Gtk.Align.CENTER)
    art.set_valign(Gtk.Align.CENTER)
    art.set_can_shrink(True)
    if hasattr(art, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        art.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(art, "set_keep_aspect_ratio"):
        art.set_keep_aspect_ratio(False)
    if image_url and load_art:
        image_loader.load_album_art_async(
            art,
            image_url,
            art_size,
            app.auth_token,
            app.image_executor,
            app.get_cache_dir(),
        )

    album_title = Gtk.Label(label=title, xalign=0.5)
    album_title.add_css_class("album-title")
    album_title.set_ellipsize(Pango.EllipsizeMode.END)
    album_title.set_justify(Gtk.Justification.CENTER)
    album_title.set_max_width_chars(24)

    art_overlay = Gtk.Overlay()
    art_overlay.set_child(art)
    if enable_album_actions:
        play_overlay = Gtk.Button()
        play_overlay.add_css_class("album-card-play-overlay")
        play_overlay.set_halign(Gtk.Align.CENTER)
        play_overlay.set_valign(Gtk.Align.CENTER)
        play_overlay.set_tooltip_text("Play album")
        play_overlay.set_child(
            Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        )
        play_overlay.connect(
            "clicked",
            lambda _button: app.on_album_card_play_clicked(card.album_data),
        )
        art_overlay.add_overlay(play_overlay)

        motion = Gtk.EventControllerMotion.new()
        motion.connect(
            "enter",
            lambda *_args: play_overlay.add_css_class("album-art-hovered"),
        )
        motion.connect(
            "leave",
            lambda *_args: play_overlay.remove_css_class("album-art-hovered"),
        )
        art_overlay.add_controller(motion)

    if provider_domain:
        badge_label = Gtk.Label(label=format_provider_badge(provider_domain))
        badge_label.add_css_class("provider-badge")
        badge_label.set_halign(Gtk.Align.END)
        badge_label.set_valign(Gtk.Align.END)
        badge_label.set_margin_end(6)
        badge_label.set_margin_bottom(6)
        art_overlay.add_overlay(badge_label)

    card.append(art_overlay)
    card.append(album_title)
    if show_artist:
        album_artist = Gtk.Label(label=artist, xalign=0.5)
        album_artist.add_css_class("album-artist")
        album_artist.set_ellipsize(Pango.EllipsizeMode.END)
        album_artist.set_justify(Gtk.Justification.CENTER)
        album_artist.set_max_width_chars(24)
        card.append(album_artist)

    if enable_album_actions:
        context_gesture = Gtk.GestureClick.new()
        context_gesture.set_button(3)
        context_gesture.connect(
            "pressed",
            lambda _gesture, _n_press, x, y: _show_album_context_menu(
                app, card, x, y
            ),
        )
        card.add_controller(context_gesture)
    return card


def make_home_album_card(
    app,
    album: dict,
    art_size: int = HOME_ALBUM_ART_SIZE,
    provider_domain: str | None = None,
) -> Gtk.Widget:
    title = app.get_album_name(album)
    artist_label = ui_utils.format_artist_names(album.get("artists") or [])
    image_url = image_loader.extract_album_image_url(album, app.server_url)
    if not provider_domain:
        provider_domain = get_album_provider_domain(album)
    return make_album_card(
        app,
        title,
        artist_label,
        image_url,
        art_size=art_size,
        provider_domain=provider_domain,
        album_data=album,
    )


def make_playlist_card(
    app,
    title: str,
    image_url: str | None = None,
    art_size: int = MEDIA_TILE_SIZE,
    load_art: bool = True,
) -> Gtk.Widget:
    return make_album_card(
        app,
        title,
        "",
        image_url,
        art_size=art_size,
        card_class="playlist-card",
        show_artist=False,
        load_art=load_art,
        enable_album_actions=False,
    )


def format_provider_badge(provider_domain: str) -> str:
    text = (provider_domain or "").strip()
    if not text:
        return ""
    if text.casefold() == "filesystem":
        return "Local"
    return text.upper()


def get_album_provider_domain(album: object) -> str | None:
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


def _show_album_context_menu(
    app,
    card: Gtk.Widget,
    x: float,
    y: float,
) -> None:
    popover = getattr(card, "context_popover", None)
    if popover is None:
        popover = Gtk.Popover()
        popover.set_has_arrow(False)
        popover.add_css_class("track-action-popover")
        action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        action_box.set_margin_start(6)
        action_box.set_margin_end(6)
        action_box.set_margin_top(6)
        action_box.set_margin_bottom(6)
        for action in (
            "Play",
            "Play Next",
            "Add to Queue",
            "Add to Playlist",
            "Start Radio",
        ):
            action_button = Gtk.Button(label=action)
            action_button.set_halign(Gtk.Align.FILL)
            action_button.set_hexpand(True)
            action_button.add_css_class("track-action-item")
            action_button.connect(
                "clicked",
                lambda button, action_label=action: app.on_album_card_context_action(
                    button,
                    popover,
                    action_label,
                    card.album_data,
                ),
            )
            action_box.append(action_button)
        popover.set_child(action_box)
        ui_utils.attach_context_popover(card, popover)
    if hasattr(popover, "set_pointing_to"):
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
    popover.popup()
