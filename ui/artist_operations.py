import threading

from gi.repository import GLib, Gtk

from constants import MEDIA_TILE_SIZE
from music_assistant_client import MusicAssistantClient
from ui import image_loader, ui_utils
from ui import track_utils
from ui.widgets import album_card
from ui.widgets.track_row import TrackRow


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
    _start_artist_top_tracks_refresh(app, artist, artist_name)


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
            art_size=MEDIA_TILE_SIZE,
            album_data=album,
        )
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(MEDIA_TILE_SIZE, -1)
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


def _start_artist_top_tracks_refresh(
    app,
    artist: object,
    artist_name: str,
) -> None:
    if not getattr(app, "artist_tracks_store", None):
        return
    app.artist_tracks_store.remove_all()
    if not app.server_url:
        return
    provider = _get_artist_provider(artist)
    thread = threading.Thread(
        target=_load_artist_top_tracks_worker,
        args=(app, artist, artist_name, provider),
        daemon=True,
    )
    thread.start()


def _load_artist_top_tracks_worker(
    app,
    artist: object,
    artist_name: str,
    provider: str | None,
) -> None:
    error = ""
    tracks: list[dict] = []
    try:
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_artist_top_tracks_async,
            artist_name,
            provider,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_artist_top_tracks_loaded, artist, tracks, error)


async def _fetch_artist_top_tracks_async(
    app,
    client: MusicAssistantClient,
    artist_name: str,
    provider: str | None,
) -> list[dict]:
    if provider:
        tracks = await client.music.get_artist_tracks(artist_name, provider)
    else:
        tracks = await client.music.get_artist_tracks(artist_name)
    describe_quality = lambda item: track_utils.describe_track_quality(
        item,
        track_utils.format_sample_rate,
    )
    serialized: list[dict] = []
    for index, track in enumerate(tracks or [], start=1):
        payload = track_utils.serialize_track(
            track,
            "",
            ui_utils.format_artist_names,
            track_utils.format_duration,
            describe_quality,
        )
        payload["track_number"] = index
        image_url = image_loader.resolve_media_item_image_url(
            client,
            track,
            app.server_url,
        )
        if image_url:
            payload["image_url"] = image_url
        serialized.append(payload)
    return serialized


def on_artist_top_tracks_loaded(
    app,
    artist: object,
    tracks: list[dict],
    error: str,
) -> None:
    if normalize_artist_name(get_artist_name(artist)) != normalize_artist_name(
        get_artist_name(getattr(app, "current_artist", None))
    ):
        return
    if error:
        return
    _populate_artist_tracks_store(app, tracks)


def _populate_artist_tracks_store(app, tracks: list[dict]) -> None:
    store = getattr(app, "artist_tracks_store", None)
    if store is None:
        return
    store.remove_all()
    for track in tracks:
        row = TrackRow(
            track_number=track.get("track_number", 0),
            title=track.get("title", ""),
            length_display=track.get("length_display", ""),
            length_seconds=track.get("length_seconds", 0),
            artist=track.get("artist", ""),
            album=track.get("album", ""),
            quality=track.get("quality", ""),
            is_favorite=bool(track.get("is_favorite", False)),
        )
        row.source = track.get("source")
        image_url = track.get("image_url")
        if image_url:
            row.image_url = image_url
        store.append(row)
    if getattr(app, "artist_tracks_view", None) and getattr(
        app,
        "artist_tracks_selection",
        None,
    ):
        app.artist_tracks_view.set_model(app.artist_tracks_selection)


def _get_artist_provider(artist: object) -> str | None:
    if isinstance(artist, dict):
        provider = (
            artist.get("provider")
            or artist.get("provider_instance")
            or artist.get("provider_domain")
        )
    else:
        provider = (
            getattr(artist, "provider", None)
            or getattr(artist, "provider_instance", None)
            or getattr(artist, "provider_domain", None)
        )
    if isinstance(provider, str):
        provider = provider.strip()
    return provider or None
