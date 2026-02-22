"""Playlist detail operations and track loading."""

import logging
import threading
from collections import OrderedDict

from gi.repository import GLib

from constants import DETAIL_ART_SIZE
from music_assistant_client import MusicAssistantClient
from music_assistant_client.exceptions import (
    CannotConnect,
    InvalidServerVersion,
    MusicAssistantClientException,
)
from music_assistant_models.errors import AuthenticationFailed, AuthenticationRequired
from ui import image_loader, toast, track_utils, ui_utils
from ui.widgets.track_row import TrackRow


EMPTY_PLAYLIST_MESSAGE = (
    "Add songs to the playlist to have them display here"
)
PLAYLIST_TRACKS_CACHE_LIMIT = 12


def _get_playlist_tracks_cache(app) -> OrderedDict:
    cache = getattr(app, "playlist_tracks_cache", None)
    if cache is None:
        cache = OrderedDict()
        app.playlist_tracks_cache = cache
    return cache


def _get_playlist_tracks_inflight(app) -> set:
    inflight = getattr(app, "playlist_tracks_inflight", None)
    if inflight is None:
        inflight = set()
        app.playlist_tracks_inflight = inflight
    return inflight


def _get_playlist_request_ids(app) -> dict:
    request_ids = getattr(app, "playlist_tracks_request_ids", None)
    if request_ids is None:
        request_ids = {}
        app.playlist_tracks_request_ids = request_ids
    return request_ids


def _make_playlist_cache_key(
    app, item_id: str, provider: str
) -> tuple[str, str, str]:
    return (app.server_url or "", str(item_id), str(provider))


def _get_cached_playlist_tracks(
    app, cache_key: tuple[str, str, str]
) -> list[dict] | None:
    cache = _get_playlist_tracks_cache(app)
    tracks = cache.get(cache_key)
    if tracks is not None:
        cache.move_to_end(cache_key)
    return tracks


def _store_playlist_tracks_cache(
    app, cache_key: tuple[str, str, str], tracks: list[dict]
) -> None:
    cache = _get_playlist_tracks_cache(app)
    cache[cache_key] = tracks
    cache.move_to_end(cache_key)
    while len(cache) > PLAYLIST_TRACKS_CACHE_LIMIT:
        cache.popitem(last=False)


def show_playlist_detail(app, playlist: dict) -> None:
    app.current_playlist = playlist
    app.current_album = playlist
    name = get_playlist_name(playlist)
    if app.playlist_detail_title:
        app.playlist_detail_title.set_label(name)
    set_playlist_editable_state(app, playlist)
    clear_playlist_detail_art(app)
    load_playlist_tracks(app, playlist)


def set_playlist_detail_status(app, message: str) -> None:
    if not app.playlist_detail_status_label:
        return
    app.playlist_detail_status_label.set_label(message)
    app.playlist_detail_status_label.set_visible(bool(message))


def set_playlist_editable_state(app, playlist: dict) -> None:
    is_editable = _is_editable_playlist(playlist)
    app.playlist_detail_is_editable = is_editable
    badge = getattr(app, "playlist_detail_read_only_badge", None)
    if badge:
        badge.set_visible(not is_editable)
    for attr in ("playlist_detail_rename_button", "playlist_detail_delete_button"):
        button = getattr(app, attr, None)
        if button:
            button.set_sensitive(is_editable)


def update_playlist_play_button(app) -> None:
    can_play = bool(app.current_album_tracks) and bool(app.server_url)
    button = getattr(app, "playlist_detail_play_button", None)
    if button:
        button.set_sensitive(can_play)
        button.set_visible(can_play)
    shuffle_button = getattr(app, "playlist_detail_shuffle_button", None)
    if shuffle_button:
        shuffle_button.set_sensitive(can_play)
        shuffle_button.set_visible(can_play)


def _start_playlist_playback(app) -> bool:
    if not app.server_url or not app.current_album_tracks:
        return False
    app.playback_album = app.current_album
    app.playback_album_tracks = [
        track_utils.snapshot_track(item, track_utils.get_track_identity)
        for item in app.current_album_tracks
    ]
    app.start_playback_from_index(0, reset_queue=True)
    return True


def on_playlist_play_clicked(app, _button) -> None:
    _start_playlist_playback(app)


def on_playlist_shuffle_clicked(app, _button) -> None:
    if not _start_playlist_playback(app):
        return
    if hasattr(app, "set_shuffle_enabled"):
        app.set_shuffle_enabled(True)


def load_playlist_tracks(
    app, playlist: dict, force_refresh: bool = False
) -> None:
    if not app.server_url:
        populate_playlist_track_table(app, [])
        set_playlist_detail_status(
            app,
            "Connect to your Music Assistant server to load playlists.",
        )
        return

    item_id, provider, _uri = get_playlist_identity(playlist)
    if not item_id or not provider:
        populate_playlist_track_table(app, [])
        set_playlist_detail_status(
            app,
            "Track details are unavailable for this playlist.",
        )
        return

    cache_key = _make_playlist_cache_key(app, item_id, provider)
    cached_tracks = _get_cached_playlist_tracks(app, cache_key)
    if cached_tracks:
        update_playlist_detail_art(app, cached_tracks)
        populate_playlist_track_table(app, cached_tracks)
        set_playlist_detail_status(app, "")
    else:
        populate_playlist_track_table(app, [])
        set_playlist_detail_status(app, "Loading tracks...")

    inflight = _get_playlist_tracks_inflight(app)
    if cache_key in inflight and not force_refresh:
        return
    inflight.discard(cache_key)
    inflight.add(cache_key)
    request_ids = _get_playlist_request_ids(app)
    request_id = request_ids.get(cache_key, 0) + 1
    request_ids[cache_key] = request_id
    thread = threading.Thread(
        target=app._load_playlist_tracks_worker,
        args=(playlist, item_id, provider, cache_key, request_id),
        daemon=True,
    )
    thread.start()


def _load_playlist_tracks_worker(
    app,
    playlist: dict,
    item_id: str,
    provider: str,
    cache_key: tuple[str, str, str],
    request_id: int,
) -> None:
    error = ""
    tracks: list[dict] = []
    try:
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_playlist_tracks_async,
            item_id,
            provider,
            get_playlist_name(playlist),
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
    GLib.idle_add(
        app.on_playlist_tracks_loaded,
        playlist,
        tracks,
        error,
        cache_key,
        request_id,
    )


async def _fetch_playlist_tracks_async(
    app, client: MusicAssistantClient, item_id: str, provider: str, playlist_name: str
) -> list[dict]:
    tracks: list[object] = []
    page = 0
    seen: set[tuple] = set()
    cover_urls: list[str] = []

    def track_identity(track: object) -> tuple:
        position = getattr(track, "position", None)
        if position is not None:
            return ("position", int(position))
        uri = getattr(track, "uri", None)
        if uri:
            return ("uri", uri)
        item_id_value = getattr(track, "item_id", None)
        if item_id_value:
            return ("item_id", item_id_value)
        title = getattr(track, "name", "") or ""
        artist = getattr(track, "artist_str", "") or ""
        return ("fallback", title, artist)

    while True:
        page_tracks = await client.music.get_playlist_tracks(
            item_id,
            provider,
            page=page,
        )
        if not page_tracks:
            break
        identities = [track_identity(track) for track in page_tracks]
        if page > 0 and not any(identity not in seen for identity in identities):
            break
        tracks.extend(page_tracks)
        seen.update(identities)
        page += 1
    cover_urls = await fetch_playlist_cover_urls(
        client, tracks, app.server_url, limit=4
    )

    describe_quality = lambda item: track_utils.describe_track_quality(
        item, track_utils.format_sample_rate
    )
    serialized: list[dict] = []
    for index, track in enumerate(tracks, start=1):
        payload = track_utils.serialize_track(
            track,
            playlist_name,
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
        if index <= len(cover_urls):
            payload["cover_image_url"] = cover_urls[index - 1]
        serialized.append(payload)
    return serialized


async def fetch_playlist_cover_urls(
    client: MusicAssistantClient,
    tracks: list[object],
    server_url: str,
    limit: int = 4,
) -> list[str]:
    image_urls: list[str] = []
    for track in tracks[:limit]:
        album_url = await fetch_track_album_cover_url(
            client,
            track,
            server_url,
        )
        if album_url:
            image_urls.append(album_url)
    return image_urls


async def fetch_track_album_cover_url(
    client: MusicAssistantClient,
    track: object,
    server_url: str,
) -> str | None:
    direct = image_loader.resolve_media_item_image_url(
        client,
        track,
        server_url,
    )
    if direct:
        return direct
    candidates = get_track_album_candidates(track)
    for album_id, album_provider in candidates:
        try:
            album = await client.music.get_album(album_id, album_provider)
        except Exception:
            album = None
        if album is None:
            continue
        image_url = None
        try:
            image_url = client.get_media_item_image_url(album)
        except Exception:
            image_url = None
        resolved = image_loader.resolve_image_url(image_url, server_url)
        if resolved:
            return resolved
    return image_loader.extract_media_image_url(track, server_url)


def get_track_album_candidates(track: object) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_candidate(
        item_id: str | None, provider: str | None
    ) -> None:
        if not item_id or not provider:
            return
        key = (str(item_id), str(provider))
        if key in seen:
            return
        seen.add(key)
        candidates.append((str(item_id), str(provider)))

    def read_album(album: object, fallback_provider: str | None) -> None:
        if not album or isinstance(album, str):
            return
        if isinstance(album, dict):
            item_id = album.get("item_id") or album.get("id")
            provider = (
                album.get("provider")
                or album.get("provider_instance")
                or album.get("provider_domain")
                or fallback_provider
            )
        else:
            item_id = getattr(album, "item_id", None) or getattr(album, "id", None)
            provider = (
                getattr(album, "provider", None)
                or getattr(album, "provider_instance", None)
                or getattr(album, "provider_domain", None)
                or fallback_provider
            )
        add_candidate(item_id, provider)

    if isinstance(track, dict):
        fallback_provider = track.get("provider")
        read_album(track.get("album"), fallback_provider)
        add_candidate(
            track.get("album_item_id") or track.get("album_id"),
            track.get("album_provider") or fallback_provider,
        )
    else:
        fallback_provider = getattr(track, "provider", None)
        read_album(getattr(track, "album", None), fallback_provider)
        add_candidate(
            getattr(track, "album_item_id", None) or getattr(track, "album_id", None),
            getattr(track, "album_provider", None) or fallback_provider,
        )
    return candidates


def on_playlist_tracks_loaded(
    app,
    playlist: dict,
    tracks: list[dict],
    error: str,
    cache_key: tuple[str, str, str] | None = None,
    request_id: int | None = None,
) -> None:
    if cache_key is not None:
        inflight = getattr(app, "playlist_tracks_inflight", None)
        if inflight:
            inflight.discard(cache_key)
        if request_id is not None:
            current_request_id = _get_playlist_request_ids(app).get(cache_key)
            if current_request_id is not None and request_id != current_request_id:
                return
    if not app.is_same_album(playlist, app.current_playlist):
        return
    logging.getLogger(__name__).debug(
        "Tracks loaded for %s: %s",
        get_playlist_name(playlist),
        len(tracks),
    )
    if error:
        logging.getLogger(__name__).debug(
            "Playlist track load error for %s: %s",
            get_playlist_name(playlist),
            error,
        )
        if (
            app.playlist_tracks_store
            and app.playlist_tracks_store.get_n_items() == 0
        ):
            populate_playlist_track_table(app, [])
        set_playlist_detail_status(app, f"Unable to load tracks: {error}")
        return

    if cache_key is not None:
        _store_playlist_tracks_cache(app, cache_key, tracks)
    update_playlist_detail_art(app, tracks)
    populate_playlist_track_table(app, tracks)
    if tracks:
        set_playlist_detail_status(app, "")
    else:
        set_playlist_detail_status(app, EMPTY_PLAYLIST_MESSAGE)


def populate_playlist_track_table(app, tracks: list[dict]) -> None:
    if app.playlist_tracks_store is None:
        return
    app.playlist_tracks_store.remove_all()
    app.current_album_tracks = []
    app.clear_track_selection(app.playlist_tracks_selection)
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
        cover_image_url = track.get("cover_image_url")
        if cover_image_url:
            row.cover_image_url = cover_image_url
        track_image_url = track.get("image_url") or cover_image_url
        if not track_image_url:
            source = track.get("source")
            if source is not None:
                track_image_url = image_loader.extract_media_image_url(
                    source,
                    app.server_url,
                )
        if track_image_url:
            row.image_url = track_image_url
        app.playlist_tracks_store.append(row)
        app.current_album_tracks.append(row)
    if app.playlist_tracks_view and app.playlist_tracks_selection:
        app.playlist_tracks_view.set_model(app.playlist_tracks_selection)
    app.sync_playback_highlight()
    update_playlist_play_button(app)
    logging.getLogger(__name__).debug(
        "Playlist track store items: %s sort model items: %s",
        app.playlist_tracks_store.get_n_items(),
        app.playlist_tracks_sort_model.get_n_items()
        if app.playlist_tracks_sort_model
        else 0,
    )


def clear_playlist_detail_art(app) -> None:
    for picture in (app.playlist_detail_art, app.playlist_detail_background):
        if not picture:
            continue
        picture.set_paintable(None)
        try:
            picture.expected_image_urls = None
        except Exception:
            pass


def update_playlist_detail_art(app, tracks: list[dict]) -> None:
    if not (app.playlist_detail_art or app.playlist_detail_background):
        return
    image_urls = collect_playlist_cover_urls(tracks, app.server_url)
    if not image_urls:
        clear_playlist_detail_art(app)
        return
    if app.playlist_detail_art:
        app.playlist_detail_art.set_paintable(None)
        image_loader.load_playlist_cover_async(
            app.playlist_detail_art,
            image_urls,
            DETAIL_ART_SIZE,
            app.auth_token,
            app.image_executor,
            app.get_cache_dir(),
        )
    if app.playlist_detail_background:
        app.playlist_detail_background.set_paintable(None)
        image_loader.load_playlist_background_async(
            app.playlist_detail_background,
            image_urls,
            app.auth_token,
            app.image_executor,
            app.get_cache_dir(),
        )


def collect_playlist_cover_urls(
    tracks: list[dict], server_url: str, limit: int = 4
) -> list[str]:
    image_urls: list[str] = []
    seen_tracks = 0
    for track in tracks:
        if not isinstance(track, dict):
            continue
        if seen_tracks >= limit:
            break
        seen_tracks += 1
        image_url = track.get("cover_image_url") or track.get("image_url")
        if not image_url:
            source = track.get("source")
            if source is not None:
                image_url = image_loader.extract_media_image_url(
                    source,
                    server_url,
                )
        if image_url:
            image_urls.append(image_url)
    return image_urls


def remove_track_from_playlist(app, track) -> None:
    playlist = app.current_playlist
    if not playlist:
        return
    if not app.server_url:
        toast.show_toast(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    if not _is_editable_playlist(playlist):
        toast.show_toast(
            app,
            "This playlist cannot be edited.",
            is_error=True,
        )
        return
    playlist_id = _get_playlist_id(playlist)
    if playlist_id is None:
        toast.show_toast(
            app,
            "Unable to remove track: missing playlist ID.",
            is_error=True,
        )
        return
    position = _get_track_position(track)
    if position is None:
        toast.show_toast(
            app,
            "Unable to remove track: missing playlist position.",
            is_error=True,
        )
        return
    playlist_name = get_playlist_name(playlist)
    toast.show_toast(app, f"Removing from {playlist_name}...")
    thread = threading.Thread(
        target=_remove_track_from_playlist_worker,
        args=(app, playlist_id, playlist_name, position),
        daemon=True,
    )
    thread.start()


def _remove_track_from_playlist_worker(
    app,
    playlist_id: str | int,
    playlist_name: str,
    position: int,
) -> None:
    error = ""
    try:
        app.client_session.run(
            app.server_url,
            app.auth_token,
            _remove_track_from_playlist_async,
            playlist_id,
            position,
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
    GLib.idle_add(
        on_track_removed_from_playlist,
        app,
        playlist_id,
        playlist_name,
        error,
    )


async def _remove_track_from_playlist_async(
    client, playlist_id: str | int, position: int
) -> None:
    await client.music.remove_playlist_tracks(playlist_id, (position,))


def on_track_removed_from_playlist(
    app, playlist_id: str | int, playlist_name: str, error: str
) -> None:
    if error:
        toast.show_toast(
            app,
            f"Unable to remove track: {error}",
            is_error=True,
        )
        return
    toast.show_toast(app, f"Removed from {playlist_name}.")
    current = app.current_playlist
    if current and _playlist_id_matches(current, playlist_id):
        app.load_playlist_tracks(current, force_refresh=True)


def get_playlist_name(playlist: object) -> str:
    if isinstance(playlist, dict):
        return playlist.get("name") or "Untitled Playlist"
    return getattr(playlist, "name", None) or "Untitled Playlist"


def get_playlist_identity(
    playlist: object,
) -> tuple[str | None, str | None, str | None]:
    if isinstance(playlist, dict):
        return (
            playlist.get("item_id") or playlist.get("id"),
            playlist.get("provider"),
            playlist.get("uri"),
        )
    return (
        getattr(playlist, "item_id", None),
        getattr(playlist, "provider", None),
        getattr(playlist, "uri", None),
    )


def _get_playlist_id(playlist: object) -> str | int | None:
    if isinstance(playlist, dict):
        return playlist.get("item_id") or playlist.get("id")
    return getattr(playlist, "item_id", None)


def _playlist_id_matches(playlist: object, playlist_id: str | int) -> bool:
    current_id = _get_playlist_id(playlist)
    if current_id is None:
        return False
    return str(current_id) == str(playlist_id)


def _is_editable_playlist(playlist: object) -> bool:
    if isinstance(playlist, dict):
        return bool(playlist.get("is_editable", False))
    return bool(getattr(playlist, "is_editable", False))


def _get_track_position(track) -> int | None:
    source = getattr(track, "source", None)
    position = getattr(source, "position", None) if source else None
    if position is None:
        return None
    try:
        return int(position)
    except (TypeError, ValueError):
        return None
