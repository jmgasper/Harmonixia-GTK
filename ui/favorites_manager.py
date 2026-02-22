"""Favorites loading and actions."""

import logging
import threading

from gi.repository import GLib
from music_assistant_client import MusicAssistantClient
from music_assistant_models.enums import MediaType

from ui import image_loader, toast, track_utils, ui_utils
from ui.widgets.track_row import TrackRow

EMPTY_FAVORITES_MESSAGE = "No favorited tracks yet."


def load_favorites(app) -> None:
    if app.favorites_loading:
        return
    if not app.server_url:
        app.populate_favorites_tracks([])
        app.set_favorites_status(
            "Connect to your Music Assistant server to load favorites.",
            is_error=True,
        )
        return
    app.favorites_loading = True
    app.set_favorites_status("Loading favorites...")
    thread = threading.Thread(
        target=app._load_favorites_worker,
        daemon=True,
    )
    thread.start()


def _load_favorites_worker(app) -> None:
    error = ""
    tracks: list[dict] = []
    try:
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_favorites_tracks_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_favorites_loaded, tracks, error)


def on_favorites_loaded(app, tracks: list[dict], error: str) -> None:
    app.favorites_loading = False
    if error:
        logging.getLogger(__name__).warning(
            "Unable to load favorites: %s",
            error,
        )
        app.populate_favorites_tracks([])
        app.set_favorites_status(
            f"Unable to load favorites: {error}",
            is_error=True,
        )
        return
    app.populate_favorites_tracks(tracks)
    if tracks:
        app.set_favorites_status("")
    else:
        app.set_favorites_status(EMPTY_FAVORITES_MESSAGE)


async def _fetch_favorites_tracks_async(
    app, client: MusicAssistantClient
) -> list[dict]:
    tracks: list[object] = []
    offset = 0
    page_size = 200
    while True:
        page = await client.music.get_library_tracks(
            favorite=True,
            limit=page_size,
            offset=offset,
        )
        if not page:
            break
        tracks.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)

    describe_quality = lambda item: track_utils.describe_track_quality(
        item, track_utils.format_sample_rate
    )
    serialized: list[dict] = []
    for index, track in enumerate(tracks, start=1):
        payload = track_utils.serialize_track(
            track,
            "Unknown Album",
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


def populate_favorites_tracks(app, tracks: list[dict]) -> None:
    if app.favorites_tracks_store is None:
        return
    app.favorites_tracks_store.remove_all()
    app.favorites_track_rows = []
    if app.favorites_tracks_selection:
        app.clear_track_selection(app.favorites_tracks_selection)
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
                    source,
                    app.server_url,
                )
        if track_image_url:
            row.image_url = track_image_url
        app.favorites_tracks_store.append(row)
        app.favorites_track_rows.append(row)
    if app.favorites_tracks_view and app.favorites_tracks_selection:
        app.favorites_tracks_view.set_model(app.favorites_tracks_selection)
    if _is_favorites_visible(app):
        app.current_album = _get_favorites_album(app)
        app.current_album_tracks = app.favorites_track_rows
    app.sync_playback_highlight()


def set_favorites_status(
    app, message: str, is_error: bool = False
) -> None:
    label = app.favorites_status_label
    if not label:
        return
    if is_error:
        label.add_css_class("error")
    else:
        label.remove_css_class("error")
    label.set_label(message)
    label.set_visible(bool(message))


def add_track_to_favorites(app, track: TrackRow) -> None:
    if not app.server_url:
        _notify_favorite_action(
            app,
            "Connect to your Music Assistant server to manage favorites.",
            is_error=True,
        )
        return
    source = getattr(track, "source", None)
    if not source:
        _notify_favorite_action(
            app,
            "Unable to add to favorites: missing track details.",
            is_error=True,
        )
        return
    _notify_favorite_action(app, "Adding to favorites...")
    thread = threading.Thread(
        target=_add_track_to_favorites_worker,
        args=(app, track, source),
        daemon=True,
    )
    thread.start()


def _add_track_to_favorites_worker(app, track: TrackRow, source: object) -> None:
    error = ""
    try:
        app.client_session.run(
            app.server_url,
            app.auth_token,
            _add_track_to_favorites_async,
            source,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(on_favorite_action_completed, app, track, True, error)


async def _add_track_to_favorites_async(
    client: MusicAssistantClient, source: object
) -> None:
    await client.music.add_item_to_favorites(source)


def remove_track_from_favorites(app, track: TrackRow) -> None:
    if not app.server_url:
        _notify_favorite_action(
            app,
            "Connect to your Music Assistant server to manage favorites.",
            is_error=True,
        )
        return
    source = getattr(track, "source", None)
    item_id = _get_track_item_id(source)
    if not item_id:
        _notify_favorite_action(
            app,
            "Unable to remove from favorites: missing track ID.",
            is_error=True,
        )
        return
    _notify_favorite_action(app, "Removing from favorites...")
    thread = threading.Thread(
        target=_remove_track_from_favorites_worker,
        args=(app, track, item_id),
        daemon=True,
    )
    thread.start()


def _remove_track_from_favorites_worker(
    app, track: TrackRow, item_id: str | int
) -> None:
    error = ""
    try:
        app.client_session.run(
            app.server_url,
            app.auth_token,
            _remove_track_from_favorites_async,
            item_id,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(on_favorite_action_completed, app, track, False, error)


async def _remove_track_from_favorites_async(
    client: MusicAssistantClient, item_id: str | int
) -> None:
    await client.music.remove_item_from_favorites(MediaType.TRACK, item_id)


def on_favorite_action_completed(
    app, track: TrackRow, is_favorite: bool, error: str
) -> None:
    action_label = (
        "add to favorites" if is_favorite else "remove from favorites"
    )
    if error:
        _notify_favorite_action(
            app,
            f"Unable to {action_label}: {error}",
            is_error=True,
        )
        return
    _set_track_favorite_state(track, is_favorite)
    if not is_favorite and _is_favorites_visible(app):
        _remove_favorite_row(app, track)
    if is_favorite:
        toast.show_toast(app, "Added to favorites.")
    else:
        toast.show_toast(app, "Removed from favorites.")
    if _is_favorites_visible(app):
        if (
            not is_favorite
            and app.favorites_tracks_store
            and app.favorites_tracks_store.get_n_items() == 0
        ):
            app.set_favorites_status(EMPTY_FAVORITES_MESSAGE)


def _set_track_favorite_state(track: TrackRow, is_favorite: bool) -> None:
    track.is_favorite = is_favorite
    source = getattr(track, "source", None)
    if source is None:
        return
    if isinstance(source, dict):
        source["favorite"] = is_favorite
        return
    if hasattr(source, "favorite"):
        try:
            source.favorite = is_favorite
        except Exception:
            pass


def _remove_favorite_row(app, track: TrackRow) -> None:
    store = app.favorites_tracks_store
    if not store:
        return
    for index in range(store.get_n_items()):
        if store.get_item(index) is track:
            store.remove(index)
            break
    app.favorites_track_rows = [
        store.get_item(index) for index in range(store.get_n_items())
    ]
    for index, row in enumerate(app.favorites_track_rows, start=1):
        row.track_number = index
    if _is_favorites_visible(app):
        app.current_album_tracks = app.favorites_track_rows
        app.sync_playback_highlight()


def _get_track_item_id(source: object) -> str | int | None:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get("item_id") or source.get("id")
    return getattr(source, "item_id", None)


def _get_favorites_album(app) -> dict:
    album = getattr(app, "favorites_album", None)
    if not album:
        album = {"name": "Favorites"}
        app.favorites_album = album
    return album


def _is_favorites_visible(app) -> bool:
    stack = getattr(app, "main_stack", None)
    if not stack:
        return False
    try:
        return stack.get_visible_child_name() == "favorites"
    except Exception:
        return False


def _notify_favorite_action(
    app, message: str, is_error: bool = False
) -> None:
    toast.show_toast(app, message, is_error=is_error)
