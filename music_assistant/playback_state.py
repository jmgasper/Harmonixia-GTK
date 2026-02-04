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


PLAYBACK_PENDING_GRACE_SECONDS = 5.0


def start_playback_from_track(app, track: TrackRow) -> None:
    if not app.current_album_tracks:
        return
    try:
        index = app.current_album_tracks.index(track)
    except ValueError:
        return
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
    app.queue_album_playback(index, force_direct_start=True)


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
    app.playback_pending = bool(
        app.playback_remote_active and _is_sendspin_output(app)
    )
    app.playback_pending_since = (
        time.monotonic() if app.playback_pending else None
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
        elif visible == "favorites" and app.favorites_tracks_selection:
            selection = app.favorites_tracks_selection
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
    app.playback_pending = False
    app.playback_pending_since = None
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
    if (
        app.favorites_tracks_selection
        and app.favorites_tracks_selection is not app.album_tracks_selection
        and app.favorites_tracks_selection is not app.playlist_tracks_selection
    ):
        app.clear_track_selection(app.favorites_tracks_selection)
    app.update_now_playing()
    app.update_playback_progress_ui()
    if app.mpris_manager:
        app.mpris_manager.notify_track_changed()


def set_playback_state(app, state: PlaybackState) -> None:
    if app.playback_state == state:
        return
    app.playback_state = state
    if state != PlaybackState.PLAYING:
        app.playback_pending = False
        app.playback_pending_since = None
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
        if getattr(app, "playback_pending", False):
            app.playback_last_tick = now
        else:
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
        album = _normalize_album_label(app.playback_track_info.get("album"))
        if not album:
            album = _extract_album_name(app.playback_track_info.get("source"))
        if not album:
            album = "Unknown Album"
        artist_label = f"{artist} / {album}"
        quality = app.playback_track_info.get("quality") or ""
        if not quality:
            source = app.playback_track_info.get("source")
            if source:
                quality = track_utils.describe_track_quality(
                    source, track_utils.format_sample_rate
                )
        if quality == "Unknown":
            quality = ""
    else:
        title = "Not Playing"
        artist = ""
        artist_label = ""
        quality = ""

    if app.now_playing_title_label:
        app.now_playing_title_label.set_label(title)
    if app.now_playing_artist_label:
        app.now_playing_artist_label.set_label(artist_label)
    if app.now_playing_quality_label:
        app.now_playing_quality_label.set_label(quality)
        app.now_playing_quality_label.set_visible(bool(quality))
    if app.now_playing_title_button:
        app.now_playing_title_button.set_sensitive(bool(app.playback_track_info))
    if app.now_playing_artist_button:
        app.now_playing_artist_button.set_sensitive(
            bool(app.playback_track_info) and bool(artist)
        )
    _update_now_playing_provider(app)
    app.update_sidebar_now_playing_art()


def _update_now_playing_provider(app) -> None:
    provider_box = getattr(app, "now_playing_provider_box", None)
    provider_label = getattr(app, "now_playing_provider_label", None)
    provider_icon = getattr(app, "now_playing_provider_icon", None)
    if not provider_box and not provider_label and not provider_icon:
        return
    if not app.playback_track_info:
        _apply_provider_badge(app, "", None, None)
        return
    source = app.playback_track_info.get("source")
    logger = logging.getLogger(__name__)
    track_title = app.playback_track_info.get("title") or "Unknown Track"
    provider_key = _extract_provider_key(source)
    mapping_count = len(_get_attr(source, "provider_mappings") or [])
    logger.info(
        "Now playing provider lookup: title=%s provider_key=%s mappings=%s",
        track_title,
        provider_key,
        mapping_count,
    )
    manifest, domain = _resolve_provider_manifest(app, source)
    if manifest is None:
        logger.info(
            "No provider manifest resolved: title=%s provider_key=%s",
            track_title,
            provider_key,
        )
        _ensure_provider_manifests_loaded(app)
        _apply_provider_badge(app, "", None, None)
        return
    label = _get_attr(manifest, "name")
    if isinstance(label, str):
        label = label.strip()
    if not label:
        label = ""
    svg_text = _pick_provider_svg(manifest)
    texture = None
    if svg_text:
        cache_key = domain or _get_attr(manifest, "domain") or "provider"
        texture = _get_cached_provider_texture(app, str(cache_key), svg_text)
    icon_name = None if texture else _get_attr(manifest, "icon")
    logger.info(
        "Resolved provider manifest: title=%s domain=%s name=%s icon=%s svg=%s",
        track_title,
        domain,
        label or _get_attr(manifest, "name"),
        icon_name,
        bool(svg_text),
    )
    _apply_provider_badge(app, label, texture, icon_name)


def _apply_provider_badge(
    app,
    label: str,
    texture: object | None,
    icon_name: object | None,
) -> None:
    provider_box = getattr(app, "now_playing_provider_box", None)
    provider_label = getattr(app, "now_playing_provider_label", None)
    provider_icon = getattr(app, "now_playing_provider_icon", None)
    has_icon = False
    if provider_icon:
        if texture is not None:
            provider_icon.set_from_paintable(texture)
            provider_icon.set_visible(True)
            has_icon = True
        elif isinstance(icon_name, str) and icon_name.strip():
            provider_icon.set_from_icon_name(icon_name.strip())
            provider_icon.set_visible(True)
            has_icon = True
        else:
            provider_icon.set_from_paintable(None)
            provider_icon.set_visible(False)
    if provider_label:
        provider_label.set_label(label)
        provider_label.set_visible(bool(label))
    if provider_box:
        provider_box.set_visible(bool(label) or has_icon)


def _ensure_provider_manifests_loaded(app) -> None:
    if not app.server_url:
        return
    if getattr(app, "provider_manifest_loading", False):
        return
    manifests = getattr(app, "provider_manifests", None)
    instances = getattr(app, "provider_instances", None)
    if manifests and instances:
        return
    logging.getLogger(__name__).info(
        "Loading provider manifests: server=%s",
        app.server_url,
    )
    app.provider_manifest_loading = True
    thread = threading.Thread(
        target=app._load_provider_manifests_worker,
        daemon=True,
    )
    thread.start()


def _resolve_provider_manifest(app, source: object | None) -> tuple[object | None, str | None]:
    manifests = getattr(app, "provider_manifests", None) or {}
    if not manifests:
        return None, None
    provider_key = _extract_provider_key(source)
    if not provider_key:
        return None, None
    if provider_key in manifests:
        return manifests[provider_key], provider_key
    instances = getattr(app, "provider_instances", None) or {}
    instance = instances.get(provider_key)
    if instance:
        domain = _get_attr(instance, "domain")
        if isinstance(domain, str):
            domain = domain.strip()
        if domain and domain in manifests:
            return manifests[domain], domain
    mappings = _get_attr(source, "provider_mappings") or []
    for mapping in mappings:
        domain = _get_attr(mapping, "provider_domain") or _get_attr(
            mapping, "provider"
        )
        if isinstance(domain, str):
            domain = domain.strip()
        if domain and domain in manifests:
            return manifests[domain], domain
    return None, None


def _extract_provider_key(source: object | None) -> str | None:
    if not source:
        return None
    for key in ("provider_instance", "provider_domain", "provider"):
        value = _get_attr(source, key)
        if isinstance(value, str):
            value = value.strip()
        if value:
            return str(value)
    return None


def _pick_provider_svg(manifest: object) -> str | None:
    for key in ("icon_svg", "icon_svg_monochrome", "icon_svg_dark"):
        value = _get_attr(manifest, key)
        if isinstance(value, str):
            value = value.strip()
        if value:
            return value
    return None


def _get_cached_provider_texture(
    app, cache_key: str, svg_text: str
) -> object | None:
    cache = getattr(app, "provider_icon_cache", None)
    if cache is None:
        app.provider_icon_cache = {}
        cache = app.provider_icon_cache
    if cache_key in cache:
        return cache[cache_key]
    texture = image_loader.load_svg_texture(svg_text)
    if texture is not None:
        cache[cache_key] = texture
    return texture


def _load_provider_manifests_worker(app) -> None:
    providers: list[object] = []
    manifests: list[object] = []
    error = ""
    try:
        providers, manifests = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_provider_manifests_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_provider_manifests_loaded, providers, manifests, error)


async def _fetch_provider_manifests_async(
    _app, client
) -> tuple[list[object], list[object]]:
    providers = await client.send_command("providers")
    manifests = await client.send_command("providers/manifests")
    return providers, manifests


def on_provider_manifests_loaded(
    app,
    providers: list[object],
    manifests: list[object],
    error: str,
) -> None:
    app.provider_manifest_loading = False
    if error:
        logging.getLogger(__name__).warning(
            "Provider manifest load failed: %s",
            error,
        )
        return
    app.provider_icon_cache = {}
    app.provider_instances = {}
    app.provider_manifests = {}
    if isinstance(providers, list):
        for item in providers:
            instance_id = _get_attr(item, "instance_id")
            if isinstance(instance_id, str):
                instance_id = instance_id.strip()
            if instance_id:
                app.provider_instances[instance_id] = item
    if isinstance(manifests, list):
        for item in manifests:
            domain = _get_attr(item, "domain")
            if isinstance(domain, str):
                domain = domain.strip()
            if domain:
                app.provider_manifests[domain] = item
    logging.getLogger(__name__).info(
        "Loaded provider details: instances=%s manifests=%s",
        len(app.provider_instances),
        len(app.provider_manifests),
    )
    if app.provider_manifests:
        sample_domains = sorted(app.provider_manifests.keys())[:5]
        logging.getLogger(__name__).debug(
            "Provider manifest domains: %s",
            sample_domains,
        )
    app.update_now_playing()


def update_sidebar_now_playing_art(app) -> None:
    if not app.sidebar_now_playing_art:
        return
    if not app.playback_track_info:
        app.sidebar_now_playing_art.set_visible(False)
        app.sidebar_now_playing_art.set_paintable(None)
        app.sidebar_now_playing_art.set_tooltip_text("Now Playing")
        app.sidebar_now_playing_art_url = None
        if getattr(app, "sidebar_queue_controls", None):
            app.sidebar_queue_controls.set_visible(False)
        try:
            app.sidebar_now_playing_art.expected_image_url = None
        except Exception:
            pass
        return
    app.sidebar_now_playing_art.set_visible(True)
    if getattr(app, "sidebar_queue_controls", None):
        app.sidebar_queue_controls.set_visible(True)

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
            "repeat_mode": None,
            "shuffle_enabled": None,
        }
    shuffle_enabled = getattr(queue, "shuffle_enabled", None)
    if shuffle_enabled is None:
        shuffle_enabled = getattr(queue, "shuffle", None)
    return {
        "state": getattr(queue, "state", None),
        "elapsed": getattr(queue, "elapsed_time", None),
        "current_item": getattr(queue, "current_item", None),
        "current_index": getattr(queue, "current_index", None),
        "repeat_mode": getattr(queue, "repeat_mode", None),
        "shuffle_enabled": shuffle_enabled,
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
    repeat_mode = payload.get("repeat_mode")
    shuffle_enabled = payload.get("shuffle_enabled")
    hold_elapsed = _should_hold_elapsed(app)

    if current_item is None:
        if _is_playback_pending_grace(app):
            return False
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
        if hold_elapsed:
            app.playback_elapsed = 0.0
        else:
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
        if updated_elapsed is not None and not hold_elapsed:
            app.playback_elapsed = updated_elapsed
            if app.playback_state == PlaybackState.PLAYING:
                app.playback_last_tick = time.monotonic()
            app.update_playback_progress_ui()

    if queue_state == "playing":
        app.set_playback_state(PlaybackState.PLAYING)
    elif queue_state == "paused":
        app.set_playback_state(PlaybackState.PAUSED)
    if (
        queue_state == "playing"
        and getattr(app, "playback_pending", False)
        and not _is_sendspin_output(app)
    ):
        mark_playback_started(app)

    _apply_queue_mode_updates(app, repeat_mode, shuffle_enabled)
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


def mark_playback_started(app) -> None:
    if not getattr(app, "playback_pending", False):
        return
    app.playback_pending = False
    app.playback_pending_since = None
    if app.playback_state == PlaybackState.PLAYING:
        app.playback_last_tick = time.monotonic()


def _is_sendspin_output(app) -> bool:
    output_manager = getattr(app, "output_manager", None)
    if not output_manager:
        return False
    player_id = getattr(output_manager, "preferred_player_id", None)
    return bool(output_manager.is_sendspin_player_id(player_id))


def _should_hold_elapsed(app) -> bool:
    return bool(getattr(app, "playback_pending", False) and _is_sendspin_output(app))


def _is_playback_pending_grace(app) -> bool:
    if not getattr(app, "playback_pending", False):
        return False
    pending_since = getattr(app, "playback_pending_since", None)
    if pending_since is None:
        return False
    return (time.monotonic() - pending_since) < PLAYBACK_PENDING_GRACE_SECONDS


def _normalize_repeat_mode(value: object) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    text = str(raw).casefold()
    if text.startswith("repeatmode."):
        text = text.split(".", 1)[1]
    if text in ("off", "none", "disabled"):
        return "off"
    if text in ("one", "track", "single"):
        return "one"
    if text in ("all", "playlist"):
        return "all"
    return None


def _normalize_shuffle_enabled(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).casefold()
    if text in ("true", "1", "yes", "on", "enabled"):
        return True
    if text in ("false", "0", "no", "off", "disabled"):
        return False
    return None


def _apply_queue_mode_updates(
    app,
    repeat_mode: object,
    shuffle_enabled: object,
) -> None:
    normalized_repeat = _normalize_repeat_mode(repeat_mode)
    if (
        normalized_repeat is not None
        and not getattr(app, "repeat_request_inflight", False)
        and normalized_repeat != getattr(app, "queue_repeat_mode", "off")
    ):
        app.queue_repeat_mode = normalized_repeat
        _update_repeat_button(app)
    normalized_shuffle = _normalize_shuffle_enabled(shuffle_enabled)
    if (
        normalized_shuffle is not None
        and not getattr(app, "shuffle_request_inflight", False)
        and normalized_shuffle != getattr(app, "queue_shuffle_enabled", False)
    ):
        app.queue_shuffle_enabled = normalized_shuffle
        _update_shuffle_button(app)


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


def _normalize_album_label(album: object | None) -> str:
    if not album:
        return ""
    if isinstance(album, str):
        return album.strip()
    if isinstance(album, dict):
        name = album.get("name") or album.get("title")
        return str(name).strip() if name else ""
    name = _get_attr(album, "name") or _get_attr(album, "title")
    if name:
        return str(name).strip()
    return ""


def _extract_album_name(item: object | None) -> str:
    if not item:
        return ""
    album = _get_attr(item, "album")
    name = _normalize_album_label(album)
    if name:
        return name
    for key in ("album_name", "album_title"):
        value = _get_attr(item, key)
        if value:
            return str(value).strip()
    return ""


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
    album = _extract_album_name(media_item)
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
    quality = track_utils.describe_track_quality(
        media_item, track_utils.format_sample_rate
    )
    identity = (
        ("uri", source_uri)
        if source_uri
        else ("fallback", track_number, title, artist)
    )
    return {
        "track_number": track_number,
        "title": title,
        "artist": artist,
        "album": album,
        "length_seconds": duration_value,
        "quality": quality,
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


def _resolve_media_uri(item: object | None) -> str | None:
    if not item:
        return None
    if isinstance(item, dict):
        uri = item.get("uri")
    else:
        uri = getattr(item, "uri", None)
    if isinstance(uri, str):
        uri = uri.strip()
    return uri or None


def _resolve_start_item(track_info: dict) -> object | None:
    if not track_info:
        return None
    source_uri = track_info.get("source_uri")
    if isinstance(source_uri, str):
        source_uri = source_uri.strip()
    if source_uri:
        return source_uri
    source = track_info.get("source")
    if source is not None:
        return source
    return None


def queue_album_playback(
    app, start_index: int, force_direct_start: bool = False
) -> None:
    if not app.playback_remote_active:
        app.playback_queue_identity = None
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Playback queue skipped: remote playback inactive."
            )
        return
    track_info = app.playback_album_tracks[start_index]
    media = _resolve_media_uri(app.playback_album)
    start_item = _resolve_start_item(track_info)
    if not media:
        media = playback.build_media_uri_list(app.playback_album_tracks)
        if not media:
            media = track_info.get("source_uri")
    if not media:
        app.playback_queue_identity = None
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Playback queue skipped: missing media payload."
            )
        return
    if os.getenv("SENDSPIN_DEBUG"):
        logging.getLogger(__name__).info(
            "Queueing playback: media=%s output=%s",
            media,
            app.output_manager.preferred_player_id
            if app.output_manager
            else None,
        )
    disable_shuffle = force_direct_start and bool(
        getattr(app, "queue_shuffle_enabled", False)
    )
    thread = threading.Thread(
        target=app._play_album_worker,
        args=(media, start_item, disable_shuffle),
        daemon=True,
    )
    thread.start()


def _play_album_worker(
    app, media: object, start_item: object | None, disable_shuffle: bool = False
) -> None:
    error = ""
    try:
        if disable_shuffle:
            try:
                playback.set_queue_shuffle(
                    app.client_session,
                    app.server_url,
                    app.auth_token,
                    False,
                    app.output_manager.preferred_player_id,
                )
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Failed to disable shuffle for direct track play: %s",
                    exc,
                )
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Starting remote playback: media=%s output=%s sendspin_connected=%s",
                media,
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
            media,
            start_item,
            app.output_manager.preferred_player_id,
        )
        if player_id:
            app.output_manager.preferred_player_id = player_id
        if disable_shuffle:
            try:
                playback.set_queue_shuffle(
                    app.client_session,
                    app.server_url,
                    app.auth_token,
                    True,
                    app.output_manager.preferred_player_id,
                )
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Failed to restore shuffle after direct track play: %s",
                    exc,
                )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning("Playback start failed: %s", error)


def send_playback_command(app, command: str, position: int | None = None) -> None:
    if not app.server_url:
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


def update_queue_controls(app) -> None:
    _update_repeat_button(app)
    _update_shuffle_button(app)


def cycle_repeat_mode(app) -> None:
    if getattr(app, "repeat_request_inflight", False):
        return
    if not app.server_url:
        return
    current = _normalize_repeat_mode(getattr(app, "queue_repeat_mode", None))
    next_mode = _next_repeat_mode(current or "off")
    app.repeat_request_inflight = True
    _update_repeat_button(app)
    thread = threading.Thread(
        target=_queue_repeat_worker,
        args=(app, next_mode),
        daemon=True,
    )
    thread.start()


def toggle_shuffle(app) -> None:
    if getattr(app, "shuffle_request_inflight", False):
        return
    if not app.server_url:
        return
    next_state = not bool(getattr(app, "queue_shuffle_enabled", False))
    app.shuffle_request_inflight = True
    _update_shuffle_button(app)
    thread = threading.Thread(
        target=_queue_shuffle_worker,
        args=(app, next_state),
        daemon=True,
    )
    thread.start()


def set_shuffle_enabled(app, enabled: bool, force: bool = False) -> None:
    if getattr(app, "shuffle_request_inflight", False):
        return
    if not app.server_url:
        return
    desired_state = bool(enabled)
    if not force:
        current = _normalize_shuffle_enabled(
            getattr(app, "queue_shuffle_enabled", None)
        )
        if current is not None and current == desired_state:
            return
    app.shuffle_request_inflight = True
    _update_shuffle_button(app)
    thread = threading.Thread(
        target=_queue_shuffle_worker,
        args=(app, desired_state),
        daemon=True,
    )
    thread.start()


def _queue_repeat_worker(app, mode: str) -> None:
    error = ""
    try:
        playback.set_queue_repeat_mode(
            app.client_session,
            app.server_url,
            app.auth_token,
            mode,
            app.output_manager.preferred_player_id
            if app.output_manager
            else None,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(_apply_repeat_result, app, mode, error)


def _apply_repeat_result(app, mode: str, error: str) -> bool:
    app.repeat_request_inflight = False
    if not error:
        app.queue_repeat_mode = mode
    _update_repeat_button(app)
    if error:
        logging.getLogger(__name__).warning(
            "Repeat mode update failed: %s",
            error,
        )
    return False


def _queue_shuffle_worker(app, enabled: bool) -> None:
    error = ""
    try:
        playback.set_queue_shuffle(
            app.client_session,
            app.server_url,
            app.auth_token,
            enabled,
            app.output_manager.preferred_player_id
            if app.output_manager
            else None,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(_apply_shuffle_result, app, enabled, error)


def _apply_shuffle_result(app, enabled: bool, error: str) -> bool:
    app.shuffle_request_inflight = False
    if not error:
        app.queue_shuffle_enabled = enabled
    _update_shuffle_button(app)
    if error:
        logging.getLogger(__name__).warning(
            "Shuffle update failed: %s",
            error,
        )
    return False


def _next_repeat_mode(current: str) -> str:
    order = ("off", "all", "one")
    current = current if current in order else "off"
    index = order.index(current)
    return order[(index + 1) % len(order)]


def _set_css_class(widget, class_name: str, enabled: bool) -> None:
    if not widget:
        return
    if enabled:
        widget.add_css_class(class_name)
    else:
        widget.remove_css_class(class_name)


def _set_queue_button_loading(stack, spinner, loading: bool) -> None:
    if not stack or not spinner:
        return
    if loading:
        spinner.start()
        stack.set_visible_child_name("spinner")
    else:
        spinner.stop()
        stack.set_visible_child_name("icon")


def _update_repeat_button(app) -> None:
    button = getattr(app, "repeat_button", None)
    if not button:
        return
    mode = _normalize_repeat_mode(getattr(app, "queue_repeat_mode", None)) or "off"
    icon_name = getattr(app, "repeat_all_icon_name", None) or "media-playlist-repeat-symbolic"
    if mode == "one":
        icon_name = (
            getattr(app, "repeat_one_icon_name", None) or icon_name
        )
    icon = getattr(app, "repeat_button_icon", None)
    if icon:
        icon.set_from_icon_name(icon_name)
    if mode == "one":
        tooltip = "Repeat one"
    elif mode == "all":
        tooltip = "Repeat all"
    else:
        tooltip = "Repeat off"
    button.set_tooltip_text(tooltip)
    _set_css_class(button, "off", mode == "off")
    _set_queue_button_loading(
        getattr(app, "repeat_button_stack", None),
        getattr(app, "repeat_button_spinner", None),
        getattr(app, "repeat_request_inflight", False),
    )
    button.set_sensitive(not getattr(app, "repeat_request_inflight", False))


def _update_shuffle_button(app) -> None:
    button = getattr(app, "shuffle_button", None)
    if not button:
        return
    enabled = bool(getattr(app, "queue_shuffle_enabled", False))
    icon_name = getattr(app, "shuffle_icon_name", None) or "media-playlist-shuffle-symbolic"
    icon = getattr(app, "shuffle_button_icon", None)
    if icon:
        icon.set_from_icon_name(icon_name)
    button.set_tooltip_text("Shuffle on" if enabled else "Shuffle off")
    _set_css_class(button, "off", not enabled)
    _set_queue_button_loading(
        getattr(app, "shuffle_button_stack", None),
        getattr(app, "shuffle_button_spinner", None),
        getattr(app, "shuffle_request_inflight", False),
    )
    button.set_sensitive(not getattr(app, "shuffle_request_inflight", False))
