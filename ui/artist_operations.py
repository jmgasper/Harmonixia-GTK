from gi.repository import Gtk

from constants import HOME_ALBUM_ART_SIZE
from ui import image_loader, ui_utils
from ui.widgets import album_card


def on_artist_row_activated(
    app,
    listbox: Gtk.ListBox,
    row: Gtk.ListBoxRow | None,
) -> None:
    if not row:
        return
    artist = getattr(row, "artist_data", None)
    if not artist:
        return
    previous_view = None
    if listbox is app.search_artists_list:
        previous_view = "search"
    elif listbox is app.artists_list:
        previous_view = "artists"
    elif app.main_stack:
        try:
            previous_view = app.main_stack.get_visible_child_name()
        except Exception:
            previous_view = None
    app.show_artist_albums(artist, previous_view)


def show_artist_albums(
    app,
    artist: object,
    previous_view: str | None = None,
) -> None:
    app.current_artist = artist
    if previous_view:
        app.artist_albums_previous_view = previous_view
    elif not getattr(app, "artist_albums_previous_view", None):
        app.artist_albums_previous_view = "artists"
    refresh_artist_albums(app)
    if app.main_stack:
        app.main_stack.set_visible_child_name("artist-albums")


def refresh_artist_albums(app) -> None:
    artist = getattr(app, "current_artist", None)
    if not artist:
        return
    artist_name = get_artist_name(artist)
    albums = filter_artist_albums(app, artist_name)
    update_artist_albums_header(app, artist_name, len(albums))
    populate_artist_album_flow(app, albums)
    update_artist_albums_status(app, artist_name, albums)


def update_artist_albums_header(
    app,
    artist_name: str,
    album_count: int,
) -> None:
    if app.artist_albums_title:
        app.artist_albums_title.set_label(artist_name)
    if app.artist_albums_header:
        app.artist_albums_header.set_label(f"Albums ({album_count})")


def update_artist_albums_status(
    app,
    artist_name: str,
    albums: list[dict],
) -> None:
    if not app.artist_albums_status_label:
        return
    message = ""
    if not artist_name:
        message = "Select an artist to view albums."
    elif app.library_loading and not app.library_albums:
        message = "Loading library..."
    elif not albums:
        message = f"No albums found for {artist_name}."
    app.artist_albums_status_label.set_label(message)
    app.artist_albums_status_label.set_visible(bool(message))


def populate_artist_album_flow(app, albums: list[dict]) -> None:
    if not app.artist_albums_flow:
        return
    ui_utils.clear_container(app.artist_albums_flow)
    for album in albums:
        if not isinstance(album, dict):
            continue
        title = app.get_album_name(album)
        artist_label = ui_utils.format_artist_names(album.get("artists") or [])
        image_url = image_loader.extract_album_image_url(album, app.server_url)
        card = album_card.make_album_card(
            app,
            title,
            artist_label,
            image_url,
            art_size=HOME_ALBUM_ART_SIZE,
        )
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(HOME_ALBUM_ART_SIZE, -1)
        child.album_data = album
        app.artist_albums_flow.append(child)


def on_artist_album_activated(
    app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild
) -> None:
    album = getattr(child, "album_data", None)
    if not album:
        return
    app.album_detail_previous_view = "artist-albums"
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def on_artist_albums_back(app, _button: Gtk.Button) -> None:
    target_view = app.artist_albums_previous_view or "artists"
    if app.main_stack:
        app.main_stack.set_visible_child_name(target_view)


def get_artist_name(artist: object) -> str:
    if isinstance(artist, dict):
        name = artist.get("name") or artist.get("sort_name")
    else:
        name = str(artist) if artist is not None else ""
    return name or "Unknown Artist"


def filter_artist_albums(app, artist_name: str) -> list[dict]:
    normalized = normalize_artist_name(artist_name)
    if not normalized:
        return []
    albums: list[dict] = []
    for album in app.library_albums or []:
        if not isinstance(album, dict):
            continue
        artists = album.get("artists") or []
        if isinstance(artists, str):
            artists = [artists]
        for artist in artists:
            candidate = None
            if isinstance(artist, dict):
                candidate = artist.get("name") or artist.get("sort_name")
            else:
                candidate = str(artist)
            if candidate and normalize_artist_name(candidate) == normalized:
                albums.append(album)
                break
    return albums


def normalize_artist_name(name: str) -> str:
    return (name or "").strip().casefold()
