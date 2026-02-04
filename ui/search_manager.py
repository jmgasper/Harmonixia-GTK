import threading

from gi.repository import GLib, Gtk

from constants import MEDIA_TILE_SIZE, SEARCH_DEBOUNCE_MS, SEARCH_RESULT_LIMIT
from music_assistant import library
from music_assistant_client import MusicAssistantClient
from music_assistant_client.exceptions import (
    CannotConnect,
    InvalidServerVersion,
    MusicAssistantClientException,
)
from music_assistant_models.enums import MediaType
from music_assistant_models.errors import AuthenticationFailed, AuthenticationRequired
from ui import image_loader, track_utils, ui_utils
from ui.widgets import album_card
from ui.widgets.track_row import TrackRow

SEARCH_MEDIA_TYPES = [
    MediaType.PLAYLIST,
    MediaType.ALBUM,
    MediaType.ARTIST,
    MediaType.TRACK,
]


def on_search_changed(app, entry: Gtk.SearchEntry) -> None:
    query = entry.get_text().strip()
    if not query:
        app.clear_search()
        return
    app.activate_search_view()
    app.schedule_search(query)


def on_search_activated(app, entry: Gtk.SearchEntry) -> None:
    query = entry.get_text().strip()
    if not query:
        app.clear_search()
        return
    app.activate_search_view()
    if app.search_debounce_id:
        GLib.source_remove(app.search_debounce_id)
        app.search_debounce_id = None
    app._start_search(query)


def on_search_scope_toggled(app, button: Gtk.CheckButton) -> None:
    app.search_library_only = button.get_active()
    query = (app.search_query or "").strip()
    if not query and app.search_entry:
        query = app.search_entry.get_text().strip()
    if not query:
        return
    app.activate_search_view()
    if app.search_debounce_id:
        GLib.source_remove(app.search_debounce_id)
        app.search_debounce_id = None
    app._start_search(query)


def activate_search_view(app) -> None:
    if not app.search_active:
        app.search_active = True
        if app.main_stack:
            app.search_previous_view = app.main_stack.get_visible_child_name()
        app.search_previous_album = app.current_album
        app.search_previous_album_tracks = app.current_album_tracks
    if app.main_stack:
        app.main_stack.set_visible_child_name("search")


def restore_search_view(app) -> None:
    if app.main_stack:
        target = app.search_previous_view or "home"
        app.main_stack.set_visible_child_name(target)
    app.search_previous_view = None
    app.current_album = app.search_previous_album
    app.current_album_tracks = app.search_previous_album_tracks or []
    app.search_previous_album = None
    app.search_previous_album_tracks = None
    app.search_context_album = None
    app.search_track_rows = []
    app.sync_playback_highlight()


def clear_search(app) -> None:
    if app.search_debounce_id:
        GLib.source_remove(app.search_debounce_id)
        app.search_debounce_id = None
    app.search_query = ""
    app.search_request_id = (app.search_request_id or 0) + 1
    app.search_loading = False
    app.clear_search_results()
    if app.search_active:
        app.search_active = False
        current_view = ""
        if app.main_stack:
            current_view = app.main_stack.get_visible_child_name()
        if current_view == "album-detail" and app.album_detail_previous_view == "search":
            app.album_detail_previous_view = app.search_previous_view or "home"
        if current_view == "search":
            app.restore_search_view()
        else:
            app.search_previous_view = None
            app.search_previous_album = None
            app.search_previous_album_tracks = None
            app.search_context_album = None
            app.search_track_rows = []


def schedule_search(app, query: str) -> None:
    app.search_query = query
    if app.search_debounce_id:
        GLib.source_remove(app.search_debounce_id)
    app.search_debounce_id = GLib.timeout_add(
        SEARCH_DEBOUNCE_MS, app._run_search
    )


def _run_search(app) -> bool:
    app.search_debounce_id = None
    query = (app.search_query or "").strip()
    if not query:
        return False
    app._start_search(query)
    return False


def _start_search(app, query: str) -> None:
    if not query:
        return
    if not app.server_url:
        app.clear_search_results()
        app.set_search_status(
            "Connect to your Music Assistant server to search.",
            is_error=True,
        )
        return
    app.search_loading = True
    app.search_request_id = (app.search_request_id or 0) + 1
    request_id = app.search_request_id
    app.set_search_status(f"Searching for \"{query}\"...")
    thread = threading.Thread(
        target=app._search_worker,
        args=(query, request_id),
        daemon=True,
    )
    thread.start()


def _search_worker(app, query: str, request_id: int) -> None:
    error = ""
    results = _empty_results()
    try:
        results = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_search_results_async,
            query,
        )
    except AuthenticationRequired:
        error = "Authentication required. Add an access token in Settings."
    except AuthenticationFailed:
        error = "Authentication failed. Check your access token."
    except CannotConnect as exc:
        error = f"Unable to reach server at {app.server_url}: {exc}"
    except InvalidServerVersion as exc:
        error = str(exc)
    except MusicAssistantClientException as exc:
        error = str(exc)
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_search_results_loaded, query, results, error, request_id)


async def _fetch_search_results_async(
    app, client: MusicAssistantClient, query: str
) -> dict:
    try:
        library_only = bool(getattr(app, "search_library_only", True))
        search_results = await client.music.search(
            search_query=query,
            media_types=SEARCH_MEDIA_TYPES,
            limit=SEARCH_RESULT_LIMIT,
            library_only=library_only,
        )
        playlists = await _serialize_playlists(client, search_results.playlists)
        albums = await _serialize_albums(client, search_results.albums)
        artists = [library._serialize_artist(item) for item in search_results.artists]
        tracks = await _serialize_tracks(client, search_results.tracks)
        return {
            "playlists": playlists,
            "albums": albums,
            "artists": artists,
            "tracks": tracks,
        }
    except Exception:
        albums = await client.music.get_library_albums(
            search=query,
            limit=SEARCH_RESULT_LIMIT,
            offset=0,
            order_by="sort_name",
        )
        artists = await client.music.get_library_artists(
            search=query,
            limit=SEARCH_RESULT_LIMIT,
            offset=0,
            order_by="sort_name",
        )
        playlists = await client.music.get_library_playlists(
            search=query,
            limit=SEARCH_RESULT_LIMIT,
            offset=0,
            order_by="sort_name",
        )
        tracks = await client.music.get_library_tracks(
            search=query,
            limit=SEARCH_RESULT_LIMIT,
            offset=0,
            order_by="sort_name",
        )
        return {
            "playlists": await _serialize_playlists(client, playlists),
            "albums": [library._serialize_album(client, album) for album in albums],
            "artists": [library._serialize_artist(artist) for artist in artists],
            "tracks": await _serialize_tracks(client, tracks),
        }


def on_search_results_loaded(
    app,
    query: str,
    results: dict,
    error: str,
    request_id: int,
) -> None:
    if request_id != app.search_request_id:
        return
    if not app.search_active:
        return
    app.search_loading = False
    if error:
        app.clear_search_results()
        app.set_search_status(error, is_error=True)
        return
    playlists = results.get("playlists") or []
    albums = results.get("albums") or []
    artists = results.get("artists") or []
    tracks = results.get("tracks") or []
    app.search_context_album = {
        "name": "Search Results",
        "is_search": True,
        "query": query,
    }
    app.populate_search_playlists(playlists)
    app.populate_search_albums(albums)
    app.populate_search_artists(artists)
    app.populate_search_tracks(tracks)

    total = len(playlists) + len(albums) + len(artists) + len(tracks)
    if total:
        app.set_search_status("")
    else:
        app.set_search_status(f"No results for \"{query}\".")


def set_search_status(app, message: str, is_error: bool = False) -> None:
    if not app.search_status_label:
        return
    if is_error:
        app.search_status_label.add_css_class("error")
    else:
        app.search_status_label.remove_css_class("error")
    app.search_status_label.set_label(message)
    app.search_status_label.set_visible(bool(message))


def clear_search_results(app) -> None:
    if app.search_playlists_flow:
        ui_utils.clear_container(app.search_playlists_flow)
    if app.search_albums_flow:
        ui_utils.clear_container(app.search_albums_flow)
    if app.search_artists_list:
        ui_utils.clear_container(app.search_artists_list)
    if app.search_tracks_store is not None:
        app.search_tracks_store.remove_all()
    if app.search_tracks_selection:
        app.clear_track_selection(app.search_tracks_selection)
    if app.search_tracks_view and app.search_tracks_selection:
        app.search_tracks_view.set_model(app.search_tracks_selection)
    app.search_track_rows = []
    for section in (
        app.search_playlists_section,
        app.search_albums_section,
        app.search_artists_section,
        app.search_tracks_section,
    ):
        if section:
            section.set_visible(False)
    app.set_search_status("")


def populate_search_playlists(app, playlists: list[dict]) -> None:
    if not app.search_playlists_flow or not app.search_playlists_section:
        return
    ui_utils.clear_container(app.search_playlists_flow)
    for playlist in playlists:
        if isinstance(playlist, dict):
            name = playlist.get("name") or "Untitled Playlist"
            image_url = playlist.get("image_url")
        else:
            name = getattr(playlist, "name", None) or "Untitled Playlist"
            image_url = None
        if image_url:
            resolved = image_loader.resolve_image_url(image_url, app.server_url)
            if resolved:
                image_url = resolved
        card = album_card.make_playlist_card(
            app,
            name,
            image_url,
            art_size=MEDIA_TILE_SIZE,
        )
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(MEDIA_TILE_SIZE, -1)
        child.playlist_data = playlist
        app.search_playlists_flow.append(child)
    app.search_playlists_section.set_visible(bool(playlists))


def populate_search_albums(app, albums: list[dict]) -> None:
    if not app.search_albums_flow or not app.search_albums_section:
        return
    ui_utils.clear_container(app.search_albums_flow)
    for album in albums:
        if isinstance(album, dict):
            title = album.get("name") or "Unknown Album"
            artist_label = ui_utils.format_artist_names(album.get("artists") or [])
            image_url = image_loader.extract_album_image_url(album, app.server_url)
            album_data = album
        else:
            title = getattr(album, "name", None) or "Unknown Album"
            artist_label = "Unknown Artist"
            image_url = None
            album_data = album
        card = album_card.make_album_card(
            app,
            title,
            artist_label,
            image_url,
            art_size=MEDIA_TILE_SIZE,
        )
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(MEDIA_TILE_SIZE, -1)
        child.album_data = album_data
        app.search_albums_flow.append(child)
    app.search_albums_section.set_visible(bool(albums))


def populate_search_artists(app, artists: list[dict]) -> None:
    if not app.search_artists_list or not app.search_artists_section:
        return
    ui_utils.clear_container(app.search_artists_list)
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or "Unknown Artist"
        else:
            name = str(artist)
        app.search_artists_list.append(ui_utils.make_artist_row(name, artist))
    app.search_artists_section.set_visible(bool(artists))


def populate_search_tracks(app, tracks: list[dict]) -> None:
    if app.search_tracks_store is None or not app.search_tracks_section:
        return
    app.search_tracks_store.remove_all()
    app.search_track_rows = []
    if app.search_tracks_selection:
        app.clear_track_selection(app.search_tracks_selection)
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
        track_image_url = track.get("image_url") or track.get("cover_image_url")
        if not track_image_url:
            source = track.get("source")
            if source is not None:
                track_image_url = image_loader.extract_media_image_url(
                    source, app.server_url
                )
        if track_image_url:
            row.image_url = track_image_url
        app.search_tracks_store.append(row)
        app.search_track_rows.append(row)
    if app.search_tracks_view and app.search_tracks_selection:
        app.search_tracks_view.set_model(app.search_tracks_selection)
    if app.search_active and app.main_stack:
        try:
            current_view = app.main_stack.get_visible_child_name()
        except Exception:
            current_view = ""
        if current_view == "search":
            app.current_album = app.search_context_album
            app.current_album_tracks = app.search_track_rows
    app.search_tracks_section.set_visible(bool(tracks))
    app.sync_playback_highlight()


def on_search_album_activated(
    app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild
) -> None:
    album = getattr(child, "album_data", None)
    if not album:
        return
    app.album_detail_previous_view = "search"
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def on_search_playlist_activated(
    app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild
) -> None:
    playlist = getattr(child, "playlist_data", None)
    if not playlist or not app.main_stack:
        return
    app.show_playlist_detail(playlist)
    app.main_stack.set_visible_child_name("playlist-detail")
    if app.home_nav_list:
        app.home_nav_list.unselect_all()
    if app.library_list:
        app.library_list.unselect_all()
    if app.playlists_list:
        app.playlists_list.unselect_all()


def _empty_results() -> dict:
    return {"playlists": [], "albums": [], "artists": [], "tracks": []}


async def _serialize_playlists(
    client: MusicAssistantClient, playlists: list[object]
) -> list[dict]:
    serialized: list[dict] = []
    for playlist in playlists:
        data = library._serialize_playlist(playlist)
        image_url = None
        try:
            image_url = client.get_media_item_image_url(playlist)
        except Exception:
            image_url = None
        if image_url:
            data["image_url"] = image_url
        serialized.append(data)
    return serialized


async def _serialize_albums(
    client: MusicAssistantClient, albums: list[object]
) -> list[dict]:
    serialized: list[dict] = []
    for album in albums:
        full_album = await _ensure_full_album(client, album)
        serialized.append(library._serialize_album(client, full_album))
    return serialized


async def _serialize_tracks(
    client: MusicAssistantClient, tracks: list[object]
) -> list[dict]:
    serialized: list[dict] = []
    describe_quality = lambda item: track_utils.describe_track_quality(
        item, track_utils.format_sample_rate
    )
    for track in tracks:
        full_track = await _ensure_full_track(client, track)
        album_name = _pick_album_name(full_track)
        payload = track_utils.serialize_track(
            full_track,
            album_name,
            ui_utils.format_artist_names,
            track_utils.format_duration,
            describe_quality,
        )
        image_url = None
        try:
            image_url = client.get_media_item_image_url(full_track)
        except Exception:
            image_url = None
        if image_url:
            payload["image_url"] = image_url
        serialized.append(payload)
    return serialized


async def _ensure_full_album(
    client: MusicAssistantClient, album: object
) -> object:
    if getattr(album, "provider_mappings", None):
        return album
    item_id = getattr(album, "item_id", None)
    provider = getattr(album, "provider", None)
    if not item_id or not provider:
        return album
    try:
        return await client.music.get_album(item_id, provider)
    except Exception:
        return album


async def _ensure_full_track(
    client: MusicAssistantClient, track: object
) -> object:
    if getattr(track, "provider_mappings", None):
        return track
    item_id = getattr(track, "item_id", None)
    provider = getattr(track, "provider", None)
    if not item_id or not provider:
        return track
    try:
        return await client.music.get_track(item_id, provider)
    except Exception:
        return track


def _pick_album_name(track: object) -> str:
    album = getattr(track, "album", None)
    if album is None:
        return "Unknown Album"
    if isinstance(album, str):
        return album or "Unknown Album"
    return getattr(album, "name", None) or "Unknown Album"
