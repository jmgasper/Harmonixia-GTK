"""Album detail operations and track loading."""

import logging
import threading
from types import SimpleNamespace

from gi.repository import GLib, Gtk

from constants import DETAIL_ART_SIZE, DETAIL_ARTIST_AVATAR_SIZE
from music_assistant import playback
from music_assistant_client import MusicAssistantClient
from ui import image_loader, toast, track_utils, ui_utils
from ui.widgets.track_row import TrackRow


def _pick_primary_artist_name(artists: object) -> str | None:
    if not artists:
        return None
    if isinstance(artists, str):
        name = artists.strip()
        return name or None
    if not isinstance(artists, (list, tuple, set)):
        artists = [artists]
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or artist.get("sort_name")
        else:
            name = getattr(artist, "name", None) or getattr(
                artist, "sort_name", None
            )
            if not name:
                name = str(artist)
        if isinstance(name, str):
            name = name.strip()
        if name:
            return str(name)
    return None


def _coerce_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def _coerce_year(value: object) -> int | None:
    if value is None:
        return None
    if hasattr(value, "year"):
        year = _coerce_int(getattr(value, "year", None))
    elif isinstance(value, str):
        text = value.strip()
        if len(text) >= 4 and text[:4].isdigit():
            year = _coerce_int(text[:4])
        else:
            year = _coerce_int(text)
    else:
        year = _coerce_int(value)
    if year is None or year < 1000 or year > 3000:
        return None
    return year


def _extract_album_field(album: object, names: tuple[str, ...]) -> object | None:
    for name in names:
        if isinstance(album, dict):
            value = album.get(name)
        else:
            value = getattr(album, name, None)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _extract_album_release_year(album: object) -> int | None:
    direct_year = _coerce_year(
        _extract_album_field(album, ("year", "release_year", "album_year"))
    )
    if direct_year:
        return direct_year

    metadata = _extract_album_field(album, ("metadata",))
    if isinstance(metadata, dict):
        release_date = metadata.get("release_date") or metadata.get("year")
    else:
        release_date = getattr(metadata, "release_date", None) or getattr(
            metadata, "year", None
        )
    metadata_year = _coerce_year(release_date)
    if metadata_year:
        return metadata_year

    release_date = _extract_album_field(album, ("release_date",))
    return _coerce_year(release_date)


def _extract_album_track_count(album: object) -> int | None:
    count = _coerce_int(
        _extract_album_field(
            album,
            (
                "track_count",
                "tracks_count",
                "total_tracks",
                "num_tracks",
                "track_total",
            ),
        )
    )
    if count is not None and count >= 0:
        return count
    if isinstance(album, dict):
        tracks = album.get("tracks")
        if isinstance(tracks, (list, tuple, set)):
            return len(tracks)
    return None


def _extract_album_duration_seconds(album: object) -> int | None:
    duration = _coerce_int(
        _extract_album_field(
            album,
            (
                "duration_seconds",
                "total_duration_seconds",
                "duration",
                "total_duration",
                "album_duration",
            ),
        )
    )
    if duration is not None and duration >= 0:
        return duration

    duration_ms = _coerce_int(
        _extract_album_field(
            album,
            (
                "duration_ms",
                "total_duration_ms",
                "album_duration_ms",
            ),
        )
    )
    if duration_ms is not None and duration_ms >= 0:
        return int(round(duration_ms / 1000))
    return None


def _resolve_image_candidate(value: object, server_url: str) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if not (
            "://" in candidate
            or candidate.startswith("/")
            or "/" in candidate
            or "?" in candidate
        ):
            return None
        return image_loader.resolve_image_url(candidate, server_url)
    return image_loader.extract_media_image_url(value, server_url)


def _extract_primary_artist_image_url(album: object, server_url: str) -> str | None:
    direct = _extract_album_field(
        album,
        (
            "artist_image_url",
            "primary_artist_image_url",
            "artist_image",
            "primary_artist_image",
        ),
    )
    resolved = _resolve_image_candidate(direct, server_url)
    if resolved:
        return resolved

    if isinstance(album, dict):
        artists = album.get("artists")
    else:
        artists = getattr(album, "artists", None)
    if not artists:
        return None
    if isinstance(artists, (str, dict)):
        artists = [artists]
    for artist in artists:
        resolved = _resolve_image_candidate(artist, server_url)
        if resolved:
            return resolved
    return None


def _set_album_artist_image(app, image_url: str | None) -> None:
    picture = getattr(app, "album_detail_artist_image", None)
    if not picture:
        return
    picture.set_paintable(None)
    if not image_url:
        picture.set_visible(False)
        try:
            picture.expected_image_url = None
        except Exception:
            pass
        return
    picture.set_visible(True)
    image_loader.load_album_art_async(
        picture,
        image_url,
        DETAIL_ARTIST_AVATAR_SIZE,
        app.auth_token,
        app.image_executor,
        app.get_cache_dir(),
    )


def _set_album_release_year_label(app, year: int | None) -> None:
    label = getattr(app, "album_detail_release_year", None)
    if not label:
        return
    text = str(year) if year else ""
    label.set_label(text)
    label.set_visible(bool(text))


def _format_album_track_summary(
    track_count: int | None, duration_seconds: int | None
) -> str:
    parts: list[str] = []
    if track_count is not None and track_count > 0:
        suffix = "track" if track_count == 1 else "tracks"
        parts.append(f"{track_count} {suffix}")
    if duration_seconds is not None and duration_seconds > 0:
        parts.append(track_utils.format_duration(duration_seconds))
    return "  ".join(parts)


def _set_album_track_summary_label(app, text: str) -> None:
    label = getattr(app, "album_detail_track_summary", None)
    if not label:
        return
    label.set_label(text)
    label.set_visible(bool(text))


def _compute_track_totals(tracks: list[dict]) -> tuple[int, int]:
    count = len(tracks)
    duration = 0
    for track in tracks:
        seconds = _coerce_int(track.get("length_seconds"))
        if seconds and seconds > 0:
            duration += seconds
    return count, duration


def _apply_album_detail_metadata(
    app, album: object, tracks: list[dict] | None = None
) -> None:
    year = _extract_album_release_year(album)
    _set_album_release_year_label(app, year)

    track_count = _extract_album_track_count(album)
    duration_seconds = _extract_album_duration_seconds(album)

    if tracks:
        computed_count, computed_duration = _compute_track_totals(tracks)
        if computed_count >= 0:
            track_count = computed_count
        if computed_duration > 0:
            duration_seconds = computed_duration

    summary = _format_album_track_summary(track_count, duration_seconds)
    _set_album_track_summary_label(app, summary)


def show_album_detail(app, album: dict) -> None:
    app.current_album = album
    album_name = get_album_name(album)
    if isinstance(album, dict):
        artists = album.get("artists")
    else:
        artists = getattr(album, "artists", None)
    artist_label = ui_utils.format_artist_names(artists or [])
    logger = logging.getLogger(__name__)
    if isinstance(album, dict):
        logger.debug(
            "Album detail: %s (item_id=%s provider=%s mappings=%s)",
            album_name,
            album.get("item_id"),
            album.get("provider"),
            len(album.get("provider_mappings") or []),
        )
    else:
        logger.debug(
            "Album detail: %s (item_id=%s provider=%s mappings=%s)",
            album_name,
            getattr(album, "item_id", None),
            getattr(album, "provider", None),
            len(getattr(album, "provider_mappings", []) or []),
        )

    if app.album_detail_title:
        app.album_detail_title.set_label(album_name)
    if app.album_detail_artist:
        app.album_detail_artist.set_label(artist_label)
    if app.album_detail_artist_button:
        primary_artist = _pick_primary_artist_name(artists)
        app.album_detail_artist_button.set_sensitive(bool(primary_artist))

    _apply_album_detail_metadata(app, album)
    artist_image_url = _extract_primary_artist_image_url(album, app.server_url)
    _set_album_artist_image(app, artist_image_url)

    image_url = image_loader.extract_media_image_url(album, app.server_url)
    if app.album_detail_art:
        app.album_detail_art.set_paintable(None)
        if image_url:
            image_loader.load_album_art_async(
                app.album_detail_art,
                image_url,
                DETAIL_ART_SIZE,
                app.auth_token,
                app.image_executor,
                app.get_cache_dir(),
            )
        else:
            try:
                app.album_detail_art.expected_image_url = None
            except Exception:
                pass
    if app.album_detail_background:
        app.album_detail_background.set_paintable(None)
        if image_url:
            image_loader.load_album_background_async(
                app.album_detail_background,
                image_url,
                app.auth_token,
                app.image_executor,
                app.get_cache_dir(),
            )
        else:
            try:
                app.album_detail_background.expected_image_url = None
            except Exception:
                pass

    populate_track_table(app, [])
    load_album_tracks(app, album)


def set_album_detail_status(app, message: str) -> None:
    if not app.album_detail_status_label:
        return
    app.album_detail_status_label.set_label(message)
    app.album_detail_status_label.set_visible(bool(message))


def get_albums_scroll_position(app) -> float:
    if not app.albums_scroller:
        return 0.0
    adjustment = app.albums_scroller.get_vadjustment()
    if not adjustment:
        return 0.0
    return adjustment.get_value()


def restore_album_scroll(app) -> bool:
    if not app.albums_scroller:
        return False
    adjustment = app.albums_scroller.get_vadjustment()
    if not adjustment:
        return False
    adjustment.set_value(app.albums_scroll_position)
    return False


def load_album_tracks(app, album: object) -> None:
    if isinstance(album, dict) and album.get("is_sample"):
        tracks = track_utils.generate_sample_tracks(
            album, ui_utils.format_artist_names, track_utils.format_duration
        )
        populate_track_table(app, tracks)
        _apply_album_detail_metadata(app, album, tracks)
        set_album_detail_status(app, "")
        return

    candidates = get_album_track_candidates(album)
    logging.getLogger(__name__).debug(
        "Track candidates for %s: %s", get_album_name(album), candidates
    )
    if not candidates or not app.server_url:
        populate_track_table(app, [])
        _apply_album_detail_metadata(app, album, [])
        set_album_detail_status(
            app,
            "Track details are unavailable for this album.",
        )
        return

    set_album_detail_status(app, "Loading tracks...")
    thread = threading.Thread(
        target=app._load_album_tracks_worker,
        args=(album, candidates),
        daemon=True,
    )
    thread.start()


def _load_album_tracks_worker(
    app, album: object, candidates: list[tuple[str, str]]
) -> None:
    error = ""
    tracks: list[dict] = []
    try:
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_album_tracks_async,
            candidates,
            album,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_album_tracks_loaded, album, tracks, error)


async def _fetch_album_tracks_async(
    app, client: MusicAssistantClient, candidates: list[tuple[str, str]], album: object
) -> list[dict]:
    tracks: list[object] = []
    had_success = False
    last_error: Exception | None = None
    for item_id, provider in candidates:
        logging.getLogger(__name__).debug(
            "Fetching tracks: provider=%s item_id=%s",
            provider,
            item_id,
        )
    for item_id, provider in candidates:
        try:
            result = await client.music.get_album_tracks(item_id, provider)
        except Exception as exc:
            last_error = exc
            logging.getLogger(__name__).debug(
                "Track fetch failed: provider=%s item_id=%s error=%s",
                provider,
                item_id,
                exc,
            )
            continue
        had_success = True
        tracks = result
        logging.getLogger(__name__).debug(
            "Track response: provider=%s item_id=%s count=%s",
            provider,
            item_id,
            len(tracks),
        )
        if tracks:
            break
    if not had_success and last_error:
        raise last_error
    album_name = get_album_name(album)
    describe_quality = lambda item: track_utils.describe_track_quality(
        item, track_utils.format_sample_rate
    )
    return [
        track_utils.serialize_track(
            track,
            album_name,
            ui_utils.format_artist_names,
            track_utils.format_duration,
            describe_quality,
        )
        for track in tracks
    ]


def on_album_tracks_loaded(
    app, album: object, tracks: list[dict], error: str
) -> None:
    if not is_same_album(app, album, app.current_album):
        return
    logging.getLogger(__name__).debug(
        "Tracks loaded for %s: %s",
        get_album_name(album),
        len(tracks),
    )
    if error:
        logging.getLogger(__name__).debug(
            "Track load error for %s: %s", get_album_name(album), error
        )
        populate_track_table(app, [])
        _apply_album_detail_metadata(app, album, [])
        set_album_detail_status(app, f"Unable to load tracks: {error}")
        return
    populate_track_table(app, tracks)
    _apply_album_detail_metadata(app, album, tracks)
    if tracks:
        set_album_detail_status(app, "")
    else:
        logging.getLogger(__name__).debug(
            "No tracks returned for %s", get_album_name(album)
        )
        set_album_detail_status(app, "No tracks available for this album.")


def populate_track_table(app, tracks: list[dict]) -> None:
    if app.album_tracks_store is None:
        return
    app.album_tracks_store.remove_all()
    app.current_album_tracks = []
    app.clear_track_selection()
    album_image_url = image_loader.extract_media_image_url(
        app.current_album, app.server_url
    )
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
        if track_image_url:
            row.image_url = track_image_url
        elif album_image_url:
            row.image_url = album_image_url
        app.album_tracks_store.append(row)
        app.current_album_tracks.append(row)
    if app.album_tracks_view and app.album_tracks_selection:
        app.album_tracks_view.set_model(app.album_tracks_selection)
    app.sync_playback_highlight()
    logging.getLogger(__name__).debug(
        "Track store items: %s sort model items: %s",
        app.album_tracks_store.get_n_items(),
        app.album_tracks_sort_model.get_n_items()
        if app.album_tracks_sort_model
        else 0,
    )


def on_album_detail_close(app, _button: Gtk.Button) -> None:
    target_view = app.album_detail_previous_view or "albums"
    if app.main_stack:
        app.main_stack.set_visible_child_name(target_view)
    if app.album_detail_background:
        app.album_detail_background.set_paintable(None)
    if target_view == "home":
        app.clear_home_album_selection()
    elif target_view == "search":
        if app.search_albums_flow:
            app.search_albums_flow.unselect_all()
        if app.search_playlists_flow:
            app.search_playlists_flow.unselect_all()
    elif target_view == "artist-albums":
        if app.artist_albums_flow:
            app.artist_albums_flow.unselect_all()
    elif target_view == "albums":
        GLib.idle_add(app.restore_album_scroll)


def on_album_play_clicked(app, _button: Gtk.Button) -> None:
    if app.current_album_tracks:
        app.playback_album = app.current_album
        app.playback_album_tracks = [
            track_utils.snapshot_track(item, track_utils.get_track_identity)
            for item in app.current_album_tracks
        ]
        app.start_playback_from_index(0, reset_queue=True)
        return
    album_name = get_album_name(app.current_album)
    logging.getLogger(__name__).info("Play album: %s", album_name)


def on_album_add_to_queue_clicked(app, _button: Gtk.Button) -> None:
    _start_album_queue_action(
        app,
        playback.add_to_queue,
        "Add to Queue",
        "Adding album to queue...",
    )


def on_album_add_to_playlist_clicked(app, _button: Gtk.Button) -> None:
    album = getattr(app, "current_album", None)
    if not album:
        toast.show_toast(app, "No album selected.", is_error=True)
        return
    if not app.server_url:
        toast.show_toast(
            app,
            "Connect to a server to use this action.",
            is_error=True,
        )
        return
    toast.show_toast(app, "Loading album tracks...")
    thread = threading.Thread(
        target=_album_add_to_playlist_worker,
        args=(app, album),
        daemon=True,
    )
    thread.start()


def on_album_start_radio_clicked(app, _button: Gtk.Button) -> None:
    _start_album_queue_action(
        app,
        playback.play_radio,
        "Start Radio",
        "Starting album radio...",
    )


def _start_album_queue_action(
    app,
    action_fn,
    action_label: str,
    pending_message: str,
) -> None:
    album = getattr(app, "current_album", None)
    if not album:
        toast.show_toast(app, "No album selected.", is_error=True)
        return
    if not app.server_url:
        toast.show_toast(
            app,
            "Connect to a server to use this action.",
            is_error=True,
        )
        return
    toast.show_toast(app, pending_message)
    thread = threading.Thread(
        target=_album_queue_action_worker,
        args=(app, album, action_fn, action_label),
        daemon=True,
    )
    thread.start()


def _album_queue_action_worker(app, album: object, action_fn, action_label: str) -> None:
    error = ""
    try:
        media = _resolve_album_queue_media(app, album)
        action_fn(
            app.client_session,
            app.server_url,
            app.auth_token,
            media,
            app.output_manager.preferred_player_id
            if app.output_manager
            else None,
        )
        if action_fn is playback.play_radio:
            GLib.idle_add(app.refresh_remote_playback_state)
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "%s failed for %s: %s",
            action_label,
            get_album_name(album),
            error,
        )
        GLib.idle_add(
            toast.show_toast,
            app,
            f"{action_label} failed: {error}",
            True,
        )
        return
    GLib.idle_add(toast.show_toast, app, f"{action_label} complete.")


def _set_album_action_status_if_current(
    app,
    album: object,
    message: str,
) -> bool:
    if is_same_album(app, album, app.current_album):
        set_album_detail_status(app, message)
    return False


def _album_add_to_playlist_worker(app, album: object) -> None:
    error = ""
    track_rows: list[TrackRow] = []
    try:
        candidates = get_album_track_candidates(album)
        if not candidates:
            raise RuntimeError("Track details are unavailable for this album.")
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_album_tracks_async,
            candidates,
            album,
        )
        track_rows = _build_playlist_track_rows(tracks)
        if not track_rows:
            raise RuntimeError("No tracks available for this album.")
    except Exception as exc:
        error = str(exc)
    if error:
        GLib.idle_add(
            toast.show_toast,
            app,
            f"Add to Playlist failed: {error}",
            True,
        )
        return
    GLib.idle_add(_show_add_album_to_playlist_dialog, app, album, track_rows)


def _build_playlist_track_rows(tracks: list[dict]) -> list[TrackRow]:
    rows: list[TrackRow] = []
    for track in tracks:
        source = track.get("source")
        source_uri = track.get("source_uri")
        if not source_uri and source is not None:
            source_uri = getattr(source, "uri", None)
        if isinstance(source_uri, str):
            source_uri = source_uri.strip()
        if not source_uri:
            continue
        if source is None or not getattr(source, "uri", None):
            source = SimpleNamespace(uri=source_uri)
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
        row.source = source
        rows.append(row)
    return rows


def _show_add_album_to_playlist_dialog(
    app,
    album: object,
    track_rows: list[TrackRow],
) -> bool:
    if is_same_album(app, album, app.current_album):
        set_album_detail_status(app, "")
    from ui import playlist_manager

    playlist_manager.show_add_to_playlist_dialog(app, track_rows)
    return False


def _resolve_album_queue_media(app, album: object) -> object:
    tracks: list[dict] = []
    track_error: Exception | None = None
    candidates = get_album_track_candidates(album)
    if candidates:
        try:
            tracks = app.client_session.run(
                app.server_url,
                app.auth_token,
                app._fetch_album_tracks_async,
                candidates,
                album,
            )
        except Exception as exc:
            track_error = exc
            logging.getLogger(__name__).debug(
                "Track URI fetch failed for %s: %s",
                get_album_name(album),
                exc,
            )

    media: object = playback.build_media_uri_list(tracks)
    if media:
        return media

    media = _resolve_album_media(album)
    if media:
        return media

    if track_error:
        raise RuntimeError(str(track_error))
    raise RuntimeError("Album source URI unavailable")


def _resolve_album_media(album: object) -> object | None:
    if isinstance(album, dict):
        uri = album.get("uri")
        item_id = album.get("item_id") or album.get("id")
        provider = (
            album.get("provider")
            or album.get("provider_instance")
            or album.get("provider_domain")
        )
    else:
        uri = getattr(album, "uri", None)
        item_id = getattr(album, "item_id", None) or getattr(album, "id", None)
        provider = (
            getattr(album, "provider", None)
            or getattr(album, "provider_instance", None)
            or getattr(album, "provider_domain", None)
        )
    if isinstance(uri, str):
        uri = uri.strip()
    if uri:
        return uri
    if item_id and provider:
        return {
            "item_id": item_id,
            "provider": provider,
        }
    return None


def get_album_name(album: object) -> str:
    if isinstance(album, dict):
        return album.get("name") or "Unknown Album"
    return getattr(album, "name", None) or "Unknown Album"


def get_album_track_candidates(album: object) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_candidate(item_id: str | None, provider: str | None) -> None:
        if not item_id or not provider:
            return
        key = (item_id, provider)
        if key in seen:
            return
        seen.add(key)
        candidates.append(key)

    if isinstance(album, dict):
        base_item_id = album.get("item_id") or album.get("id")
        base_provider = (
            album.get("provider")
            or album.get("provider_instance")
            or album.get("provider_domain")
        )
        add_candidate(base_item_id, base_provider)
        mappings = album.get("provider_mappings") or []
        if isinstance(mappings, (list, tuple, set)):
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                mapping_item_id = mapping.get("item_id")
                mapping_provider = (
                    mapping.get("provider_instance")
                    or mapping.get("provider_domain")
                )
                add_candidate(mapping_item_id, mapping_provider)
        return candidates

    base_item_id = getattr(album, "item_id", None)
    base_provider = getattr(album, "provider", None)
    add_candidate(base_item_id, base_provider)

    mappings = getattr(album, "provider_mappings", None) or []
    for mapping in mappings:
        if isinstance(mapping, dict):
            mapping_item_id = mapping.get("item_id")
            mapping_provider = (
                mapping.get("provider_instance")
                or mapping.get("provider_domain")
            )
        else:
            mapping_item_id = getattr(mapping, "item_id", None)
            mapping_provider = (
                getattr(mapping, "provider_instance", None)
                or getattr(mapping, "provider_domain", None)
            )
        add_candidate(mapping_item_id, mapping_provider)
    return candidates


def get_album_identity(album: object) -> tuple[str | None, str | None, str | None]:
    if isinstance(album, dict):
        return (
            album.get("item_id") or album.get("id"),
            album.get("provider"),
            album.get("uri"),
        )
    return (
        getattr(album, "item_id", None),
        getattr(album, "provider", None),
        getattr(album, "uri", None),
    )


def is_same_album(_app, album: object, other: object) -> bool:
    if album is other:
        return True
    if not album or not other:
        return False
    album_id, album_provider, album_uri = get_album_identity(album)
    other_id, other_provider, other_uri = get_album_identity(other)
    if album_uri and other_uri and album_uri == other_uri:
        return True
    if album_id and other_id and album_id == other_id:
        if album_provider and other_provider:
            return album_provider == other_provider
        return True
    return False
