from gi.repository import Gtk, Pango

from constants import MEDIA_TILE_SIZE
from ui import image_loader, ui_utils


def make_album_card(
    app,
    title: str,
    artist: str,
    image_url: str | None = None,
    art_size: int = MEDIA_TILE_SIZE,
    card_class: str | None = None,
    show_artist: bool = True,
) -> Gtk.Widget:
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("album-card")
    if card_class:
        card.add_css_class(card_class)
    card.set_size_request(art_size, -1)
    card.set_halign(Gtk.Align.CENTER)
    card.set_valign(Gtk.Align.CENTER)
    card.set_hexpand(False)
    card.set_vexpand(False)

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
    if image_url:
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

    card.append(art)
    card.append(album_title)
    if show_artist:
        album_artist = Gtk.Label(label=artist, xalign=0.5)
        album_artist.add_css_class("album-artist")
        album_artist.set_ellipsize(Pango.EllipsizeMode.END)
        album_artist.set_justify(Gtk.Justification.CENTER)
        album_artist.set_max_width_chars(24)
        card.append(album_artist)
    return card


def make_home_album_card(app, album: dict) -> Gtk.Widget:
    title = app.get_album_name(album)
    artist_label = ui_utils.format_artist_names(album.get("artists") or [])
    image_url = image_loader.extract_album_image_url(album, app.server_url)
    return make_album_card(
        app,
        title,
        artist_label,
        image_url,
        art_size=MEDIA_TILE_SIZE,
    )


def make_playlist_card(
    app,
    title: str,
    image_url: str | None = None,
    art_size: int = MEDIA_TILE_SIZE,
) -> Gtk.Widget:
    return make_album_card(
        app,
        title,
        "",
        image_url,
        art_size=art_size,
        card_class="playlist-card",
        show_artist=False,
    )
