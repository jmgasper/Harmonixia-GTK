"""Playback state management and queue helpers."""

import logging
import os
import threading
import time

from gi.repository import GLib

from constants import SIDEBAR_ART_SIZE
from music_assistant import playback
from music_assistant_models.enums import PlaybackState
from ui import image_loader, track_utils, ui_utils
from ui.widgets.track_row import TrackRow


def start_playback_from_track(app, track: TrackRow) -> None:
    if not app.current_album_tracks:
        return
    try:
        index = app.current_album_tracks.index(track)
    except ValueError:
        return
    was_playing = app.playback_track_info is not None
    app.playback_album = app.current_album
    app.playback_album_tracks = [
        track_utils.snapshot_track(item, track_utils.get_track_identity)
        for item in app.current_album_tracks
    ]
    app.start_playback_from_index(index, reset_queue=False)
    if not app.playback_remote_active:
        app.playback_queue_identity = None
        return
    app.schedule_home_recently_played_refresh()
    queue_identity = tuple(
        item["identity"] for item in app.playback_album_tracks
    )
    if (
        was_playing
        and app.playback_queue_identity == queue_identity
        and app.playback_track_identity is not None
    ):
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Reusing playback queue for index=%s",
                index,
            )
        app.send_playback_index(index)
        return
    app.queue_album_playback(index)


def start_playback_from_index(app, index: int, reset_queue: bool) -> None:
    if not app.playback_album_tracks:
        return
    if index < 0 or index >= len(app.playback_album_tracks):
        return
    track_info = app.playback_album_tracks[index]
    app.playback_track_index = index
    app.playback_track_info = track_info
    app.playback_track_identity = track_info["identity"]
    app.playback_elapsed = 0.0
    app.playback_last_tick = time.monotonic()
    app.playback_duration = track_info.get("length_seconds", 0) or 0
    app.playback_remote_active = bool(
        track_info.get("source_uri") and app.server_url
    )
    if app.playback_remote_active:
        app.ensure_remote_playback_sync()
    else:
        app.stop_remote_playback_sync()
    if os.getenv("SENDSPIN_DEBUG"):
        logging.getLogger(__name__).info(
            "Playback start: title=%s source_uri=%s remote=%s output=%s",
            track_info.get("title") or "Unknown Track",
            track_info.get("source_uri"),
            app.playback_remote_active,
            app.output_manager.preferred_player_id
            if app.output_manager
            else None,
        )
    app.set_playback_state(PlaybackState.PLAYING)
    app.update_now_playing()
    if app.mpris_manager:
        app.mpris_manager.notify_track_changed()
    app.update_playback_progress_ui()
    app.ensure_playback_timer()
    app.sync_playback_highlight()
    if reset_queue:
        app.schedule_home_recently_played_refresh()
        app.queue_album_playback(index)


def handle_previous_action(app) -> None:
    if app.playback_track_info is None:
        return
    if app.playback_elapsed >= 3:
        app.restart_current_track()
        return
    if app.playback_track_index is None:
        app.restart_current_track()
        return
    prev_index = app.playback_track_index - 1
    if prev_index < 0:
        app.restart_current_track()
        return
    app.start_playback_from_index(prev_index, reset_queue=False)
    app.send_playback_command("previous")


def handle_next_action(app) -> None:
    if app.playback_track_info is None:
        return
    if app.playback_track_index is None:
        return
    next_index = app.playback_track_index + 1
    if next_index >= len(app.playback_album_tracks):
        return
    app.start_playback_from_index(next_index, reset_queue=False)
    app.send_playback_command("next")


def restart_current_track(app) -> None:
    if app.playback_track_info is None:
        return
    app.playback_elapsed = 0.0
    app.playback_last_tick = time.monotonic()
    app.update_playback_progress_ui()
    app.send_playback_command("seek", position=0)
    if app.mpris_manager:
        app.mpris_manager.emit_mpris_seeked(0)


def sync_playback_highlight(app) -> None:
    if not app.current_album_tracks:
        return
    selection = app.album_tracks_selection
    if app.main_stack:
        try:
            visible = app.main_stack.get_visible_child_name()
        except Exception:
            visible = ""
        if visible == "search" and app.search_tracks_selection:
            selection = app.search_tracks_selection
        elif (
            visible == "playlist-detail"
            and app.playlist_tracks_selection
        ):
            selection = app.playlist_tracks_selection
    for row in app.current_album_tracks:
        row.is_playing = False
    if not app.playback_track_identity:
        return
    if not app.is_same_album(app.current_album, app.playback_album):
        return
    target_index = None
    for index, row in enumerate(app.current_album_tracks):
        source = getattr(row, "source", None)
        source_uri = getattr(source, "uri", None) if source else None
        if (
            track_utils.get_track_identity(row, source_uri)
            == app.playback_track_identity
        ):
            row.is_playing = True
            target_index = index
            break
    if target_index is None or not selection:
        return
    app.suppress_track_selection = True
    selection.set_selected(target_index)
    app.suppress_track_selection = False


def stop_playback(app) -> None:
    if not app.playback_track_info and app.playback_state == PlaybackState.IDLE:
        return
    app.playback_track_info = None
    app.playback_track_identity = None
    app.playback_track_index = None
    app.playback_elapsed = 0.0
    app.playback_duration = 0
    app.playback_last_tick = None
    app.playback_remote_active = False
    app.stop_remote_playback_sync()
    app.set_playback_state(PlaybackState.IDLE)
    app.sync_playback_highlight()
    if app.album_tracks_selection:
        app.clear_track_selection(app.album_tracks_selection)
    if (
        app.playlist_tracks_selection
        and app.playlist_tracks_selection is not app.album_tracks_selection
    ):
        app.clear_track_selection(app.playlist_tracks_selection)
    app.update_now_playing()
    app.update_playback_progress_ui()
    if app.mpris_manager:
        app.mpris_manager.notify_track_changed()


def set_playback_state(app, state: PlaybackState) -> None:
    if app.playback_state == state:
        return
    app.playback_state = state
    if state == PlaybackState.PLAYING:
        app.playback_last_tick = time.monotonic()
        app.ensure_playback_timer()
    app.update_play_pause_icon()
    if app.mpris_manager:
        app.mpris_manager.notify_playback_state_changed()


def update_play_pause_icon(app) -> None:
    if not app.play_pause_image or not app.play_pause_button:
        return
    if app.playback_state == PlaybackState.PLAYING:
        app.play_pause_image.set_from_icon_name(
            "media-playback-pause-symbolic"
        )
        app.play_pause_button.set_tooltip_text("Pause")
    else:
        app.play_pause_image.set_from_icon_name(
            "media-playback-start-symbolic"
        )
        app.play_pause_button.set_tooltip_text("Play")


def ensure_playback_timer(app) -> None:
    if app.playback_timer_id is None:
        app.playback_timer_id = GLib.timeout_add(500, app.on_playback_tick)


def on_playback_tick(app) -> bool:
    if app.playback_track_info is None:
        app.playback_timer_id = None
        return False
    if app.playback_state == PlaybackState.PLAYING:
        now = time.monotonic()
        if app.playback_last_tick is None:
            app.playback_last_tick = now
        delta = now - app.playback_last_tick
        app.playback_elapsed += delta
        app.playback_last_tick = now
        if app.playback_duration:
            app.playback_elapsed = min(
                app.playback_elapsed, float(app.playback_duration)
            )
    app.update_playback_progress_ui()
    return True


def update_now_playing(app) -> None:
    if app.playback_track_info:
        title = app.playback_track_info.get("title") or "Unknown Track"
        artist = app.playback_track_info.get("artist") or "Unknown Artist"
    else:
        title = "Not Playing"
        artist = ""

    if app.now_playing_title_label:
        app.now_playing_title_label.set_label(title)
    if app.now_playing_artist_label:
        app.now_playing_artist_label.set_label(artist)
    if app.now_playing_title_button:
        app.now_playing_title_button.set_sensitive(bool(app.playback_track_info))
    if app.now_playing_artist_button:
        app.now_playing_artist_button.set_sensitive(
            bool(app.playback_track_info) and bool(artist)
        )
    app.update_sidebar_now_playing_art()


def update_sidebar_now_playing_art(app) -> None:
    if not app.sidebar_now_playing_art:
        return
    if not app.playback_track_info:
        app.sidebar_now_playing_art.set_paintable(None)
        app.sidebar_now_playing_art.set_tooltip_text("Now Playing")
        app.sidebar_now_playing_art_url = None
        try:
            app.sidebar_now_playing_art.expected_image_url = None
        except Exception:
            pass
        return

    title = app.playback_track_info.get("title") or "Unknown Track"
    artist = app.playback_track_info.get("artist") or "Unknown Artist"
    app.sidebar_now_playing_art.set_tooltip_text(f"{title} - {artist}")

    image_url = app.playback_track_info.get("image_url")
    if image_url:
        resolved = image_loader.resolve_image_url(image_url, app.server_url)
        if resolved:
            image_url = resolved
    if not image_url:
        source = app.playback_track_info.get("source")
        if source:
            image_url = image_loader.extract_media_image_url(
                source,
                app.server_url,
            )
    if not image_url and app.playback_album:
        image_url = image_loader.extract_media_image_url(
            app.playback_album,
            app.server_url,
        )
    if not image_url:
        app.sidebar_now_playing_art.set_paintable(None)
        app.sidebar_now_playing_art_url = None
        try:
            app.sidebar_now_playing_art.expected_image_url = None
        except Exception:
            pass
        return
    if image_url == app.sidebar_now_playing_art_url:
        try:
            current_paintable = app.sidebar_now_playing_art.get_paintable()
        except Exception:
            current_paintable = None
        if current_paintable is not None:
            return
    app.sidebar_now_playing_art_url = image_url
    app.sidebar_now_playing_art.set_paintable(None)
    image_loader.load_album_art_async(
        app.sidebar_now_playing_art,
        image_url,
        SIDEBAR_ART_SIZE,
        app.auth_token,
        app.image_executor,
        app.get_cache_dir(),
    )


def update_playback_progress_ui(app) -> None:
    if (
        not app.playback_progress_bar
        or not app.playback_time_current_label
        or not app.playback_time_total_label
    ):
        return
    elapsed = app.playback_elapsed if app.playback_track_info else 0
    duration = app.playback_duration if app.playback_track_info else 0
    app.playback_time_current_label.set_label(
        track_utils.format_timecode(elapsed)
    )
    app.playback_time_total_label.set_label(
        track_utils.format_timecode(duration)
    )
    fraction = 0.0
    if duration:
        fraction = max(0.0, min(1.0, elapsed / duration))
    app.playback_progress_bar.set_fraction(fraction)


def ensure_remote_playback_sync(app, interval_ms: int = 2000) -> None:
    if app.playback_sync_id is not None:
        return
    if not app.server_url:
        return
    app.playback_sync_id = GLib.timeout_add(
        interval_ms,
        app._remote_playback_sync_tick,
    )


def stop_remote_playback_sync(app) -> None:
    sync_id = app.playback_sync_id
    if sync_id is None:
        return
    try:
        GLib.source_remove(sync_id)
    except Exception:
        pass
    app.playback_sync_id = None


def _remote_playback_sync_tick(app) -> bool:
    if not app.server_url or (
        not app.playback_track_info and not app.playback_remote_active
    ):
        app.playback_sync_id = None
        return False
    if app.playback_sync_inflight:
        return True
    app.playback_sync_inflight = True
    thread = threading.Thread(
        target=app._sync_remote_playback_worker,
        daemon=True,
    )
    thread.start()
    return True


def _sync_remote_playback_worker(app) -> None:
    error = ""
    payload = None
    try:
        preferred_player_id = (
            app.output_manager.preferred_player_id
            if app.output_manager
            else None
        )
        payload = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_remote_playback_state_async,
            preferred_player_id,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app._apply_remote_playback_state, payload, error)


async def _fetch_remote_playback_state_async(
    app, client, preferred_player_id
) -> dict:
    player_id, _queue_id = await playback.resolve_player_and_queue(
        client,
        preferred_player_id,
    )
    queue = await client.player_queues.get_active_queue(player_id)
    if not queue:
        return {
            "state": None,
            "elapsed": None,
            "current_item": None,
            "current_index": None,
        }
    return {
        "state": getattr(queue, "state", None),
        "elapsed": getattr(queue, "elapsed_time", None),
        "current_item": getattr(queue, "current_item", None),
        "current_index": getattr(queue, "current_index", None),
    }


def _apply_remote_playback_state(
    app, payload: dict | None, error: str
) -> bool:
    app.playback_sync_inflight = False
    if error:
        logging.getLogger(__name__).debug(
            "Remote playback sync failed: %s",
            error,
        )
        return False
    if not payload:
        return False

    current_item = payload.get("current_item")
    queue_state = _normalize_queue_state(payload.get("state"))
    elapsed = payload.get("elapsed")
    current_index = payload.get("current_index")

    if current_item is None:
        if app.playback_track_info:
            app.stop_playback()
        return False

    track_info = _build_track_info_from_queue_item(app, current_item)
    if not track_info:
        return False

    new_index = _resolve_remote_track_index(
        app,
        track_info,
        current_index,
    )
    new_identity = track_info.get("identity")
    track_changed = (
        app.playback_track_info is None
        or new_identity != app.playback_track_identity
        or (new_index is not None and new_index != app.playback_track_index)
    )

    if track_changed:
        app.playback_track_info = track_info
        app.playback_track_identity = new_identity
        app.playback_track_index = new_index
        app.playback_duration = track_info.get("length_seconds", 0) or 0
        app.playback_elapsed = _coerce_elapsed(elapsed) or 0.0
        app.playback_last_tick = time.monotonic()
        app.playback_remote_active = bool(
            track_info.get("source_uri") and app.server_url
        )
        app.update_now_playing()
        if app.mpris_manager:
            app.mpris_manager.notify_track_changed()
        app.update_playback_progress_ui()
        app.sync_playback_highlight()
    else:
        updated_elapsed = _coerce_elapsed(elapsed)
        if updated_elapsed is not None:
            app.playback_elapsed = updated_elapsed
            if app.playback_state == PlaybackState.PLAYING:
                app.playback_last_tick = time.monotonic()
            app.update_playback_progress_ui()

    if queue_state == "playing":
        app.set_playback_state(PlaybackState.PLAYING)
    elif queue_state == "paused":
        app.set_playback_state(PlaybackState.PAUSED)

    app.ensure_playback_timer()
    return False


def _coerce_elapsed(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_queue_state(state: object) -> str:
    if state is None:
        return ""
    value = getattr(state, "value", state)
    text = str(value).casefold()
    if text.startswith("playbackstate."):
        return text.split(".", 1)[1]
    return text


def _get_attr(item: object, key: str, default: object = None) -> object:
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _extract_queue_media_item(item: object) -> object:
    for key in ("media_item", "item", "track", "media"):
        candidate = _get_attr(item, key)
        if candidate:
            return candidate
    return item


def _build_track_info_from_queue_item(
    app, queue_item: object
) -> dict | None:
    media_item = _extract_queue_media_item(queue_item)
    if media_item is None:
        return None
    title = _get_attr(media_item, "name") or _get_attr(
        media_item, "title"
    )
    if not title:
        title = "Unknown Track"
    elif not isinstance(title, str):
        title = str(title)
    artist = _get_attr(media_item, "artist_str") or _get_attr(
        media_item, "artist"
    )
    if isinstance(artist, (list, tuple)):
        artist = ui_utils.format_artist_names(list(artist))
    elif not artist:
        artists = _get_attr(media_item, "artists") or []
        names = []
        for artist_item in artists:
            name = _get_attr(artist_item, "name") or _get_attr(
                artist_item, "sort_name"
            )
            if name:
                names.append(str(name))
        artist = (
            ui_utils.format_artist_names(names)
            if names
            else "Unknown Artist"
        )
    elif not isinstance(artist, str):
        artist = str(artist)
    duration = (
        _get_attr(media_item, "duration")
        or _get_attr(media_item, "length_seconds")
        or _get_attr(media_item, "length")
        or 0
    )
    try:
        duration_value = int(duration)
    except (TypeError, ValueError):
        duration_value = 0
    track_number = _get_attr(media_item, "track_number") or 0
    try:
        track_number = int(track_number)
    except (TypeError, ValueError):
        track_number = 0
    source_uri = (
        _get_attr(media_item, "uri")
        or _get_attr(queue_item, "uri")
        or _get_attr(media_item, "source_uri")
    )
    if isinstance(source_uri, str):
        source_uri = source_uri.strip() or None
    else:
        source_uri = None
    image_url = (
        _get_attr(media_item, "image_url")
        or _get_attr(media_item, "cover_image_url")
        or _get_attr(media_item, "image")
        or _get_attr(media_item, "artwork")
    )
    if isinstance(image_url, str):
        image_url = image_url.strip() or None
    else:
        image_url = None
    identity = (
        ("uri", source_uri)
        if source_uri
        else ("fallback", track_number, title, artist)
    )
    return {
        "track_number": track_number,
        "title": title,
        "artist": artist,
        "length_seconds": duration_value,
        "source": media_item,
        "source_uri": source_uri,
        "image_url": image_url,
        "identity": identity,
    }


def _resolve_remote_track_index(
    app, track_info: dict, queue_index: object
) -> int | None:
    source_uri = track_info.get("source_uri")
    if source_uri and app.playback_album_tracks:
        for index, item in enumerate(app.playback_album_tracks):
            if item.get("source_uri") == source_uri:
                return index
    if queue_index is None or not app.playback_album_tracks:
        return None
    try:
        index = int(queue_index)
    except (TypeError, ValueError):
        return None
    if 0 <= index < len(app.playback_album_tracks):
        return index
    return None


def queue_album_playback(app, start_index: int) -> None:
    if not app.playback_remote_active:
        app.playback_queue_identity = None
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Playback queue skipped: remote playback inactive."
            )
        return
    track_info = app.playback_album_tracks[start_index]
    track_uri = track_info.get("source_uri")
    if not track_uri:
        app.playback_queue_identity = None
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Playback queue skipped: missing source URI."
            )
        return
    if os.getenv("SENDSPIN_DEBUG"):
        logging.getLogger(__name__).info(
            "Queueing playback: uri=%s output=%s",
            track_uri,
            app.output_manager.preferred_player_id
            if app.output_manager
            else None,
        )
    album_media = playback.build_media_uri_list(app.playback_album_tracks)
    if album_media:
        app.playback_queue_identity = tuple(
            item["identity"] for item in app.playback_album_tracks
        )
    else:
        app.playback_queue_identity = None
    thread = threading.Thread(
        target=app._play_album_worker,
        args=(track_uri, album_media, start_index),
        daemon=True,
    )
    thread.start()


def _play_album_worker(
    app, track_uri: str, album_media: list[str], start_index: int
) -> None:
    error = ""
    try:
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Starting remote playback: uri=%s output=%s sendspin_connected=%s",
                track_uri,
                app.output_manager.preferred_player_id
                if app.output_manager
                else None,
                app.sendspin_manager.connected
                if getattr(app, "sendspin_manager", None)
                else None,
            )
        player_id = playback.play_album(
            app.client_session,
            app.server_url,
            app.auth_token,
            track_uri,
            album_media,
            start_index,
            app.output_manager.preferred_player_id,
        )
        if player_id:
            app.output_manager.preferred_player_id = player_id
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning("Playback start failed: %s", error)


def send_playback_command(app, command: str, position: int | None = None) -> None:
    if not app.playback_remote_active:
        return
    thread = threading.Thread(
        target=app._playback_command_worker,
        args=(command, position),
        daemon=True,
    )
    thread.start()


def _playback_command_worker(app, command: str, position: int | None) -> None:
    error = ""
    try:
        playback.send_playback_command(
            app.client_session,
            app.server_url,
            app.auth_token,
            command,
            app.output_manager.preferred_player_id,
            position,
        )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "Playback command '%s' failed: %s",
            command,
            error,
        )


def send_playback_index(app, index: int) -> None:
    if not app.playback_remote_active:
        return
    thread = threading.Thread(
        target=app._playback_index_worker,
        args=(index,),
        daemon=True,
    )
    thread.start()


def _playback_index_worker(app, index: int) -> None:
    error = ""
    try:
        playback.play_index(
            app.client_session,
            app.server_url,
            app.auth_token,
            int(index),
            app.output_manager.preferred_player_id,
        )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "Playback index '%s' failed: %s",
            index,
            error,
        )
