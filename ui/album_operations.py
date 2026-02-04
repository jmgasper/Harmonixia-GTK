"""Album detail operations and track loading."""

import logging
import threading

from gi.repository import GLib, Gtk

from constants import DETAIL_ART_SIZE
from music_assistant_client import MusicAssistantClient
from ui import image_loader, track_utils, ui_utils
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
    image_url = (
        image_loader.extract_album_image_url(album, app.server_url)
        if isinstance(album, dict)
        else None
    )
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
        set_album_detail_status(app, "")
        return

    candidates = get_album_track_candidates(album)
    logging.getLogger(__name__).debug(
        "Track candidates for %s: %s", get_album_name(album), candidates
    )
    if not candidates or not app.server_url:
        populate_track_table(app, [])
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
        try:
            logging.getLogger(__name__).debug(
                "Fetching tracks: provider=%s item_id=%s",
                provider,
                item_id,
            )
            tracks = await client.music.get_album_tracks(item_id, provider)
            had_success = True
            logging.getLogger(__name__).debug(
                "Track response: provider=%s item_id=%s count=%s",
                provider,
                item_id,
                len(tracks),
            )
        except Exception as exc:
            last_error = exc
            logging.getLogger(__name__).debug(
                "Track fetch failed: provider=%s item_id=%s error=%s",
                provider,
                item_id,
                exc,
            )
            continue
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
        set_album_detail_status(app, f"Unable to load tracks: {error}")
        return
    populate_track_table(app, tracks)
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
