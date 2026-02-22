"""Library loading and artist management helpers."""

import logging
import threading

from gi.repository import GLib, Gtk

from constants import SAMPLE_ARTISTS
from music_assistant import library
from music_assistant_client.exceptions import (
    CannotConnect,
    InvalidServerVersion,
    MusicAssistantClientException,
)
from music_assistant_models.errors import AuthenticationFailed, AuthenticationRequired


def _notify_connection_result(app, error: str) -> None:
    callbacks = getattr(app, "_pending_connection_callbacks", None)
    if not callbacks or not isinstance(callbacks, dict):
        return
    on_success = callbacks.get("on_success")
    on_error = callbacks.get("on_error")
    app._pending_connection_callbacks = None
    if error:
        if callable(on_error):
            on_error(error)
    elif callable(on_success):
        on_success()


def load_library(app) -> None:
    from ui import playlist_manager

    if app.library_loading:
        return
    if not app.server_url:
        app.set_status(
            "Enter a server address in Settings.",
            is_error=True,
        )
        if app.playlists_add_button:
            app.playlists_add_button.set_sensitive(False)
        playlist_manager.populate_playlists_list(app, [])
        playlist_manager.set_playlists_status(
            app,
            "Connect to your Music Assistant server to load playlists.",
        )
        return

    if app.playlists_add_button:
        app.playlists_add_button.set_sensitive(True)
    app.playlists_loading = True
    playlist_manager.set_playlists_status(app, "Loading playlists...")
    app.library_loading = True
    if app.settings_button:
        app.settings_button.set_sensitive(False)
    app.set_loading_state(
        True,
        f"Loading library from {app.server_url}...",
    )

    thread = threading.Thread(
        target=app._load_library_worker,
        daemon=True,
    )
    thread.start()


def _load_library_worker(app) -> None:
    error = ""
    albums: list[dict] = []
    artists: list[dict] = []
    playlists: list[dict] = []
    favorite_filter = (
        True if getattr(app, "album_filter_favorite_only", False) else None
    )
    try:
        GLib.idle_add(app.set_loading_message, "Loading albums...")
        album_order = getattr(app, "album_sort_order", None) or "sort_name"
        albums, artists, playlists = app.client_session.run(
            app.server_url,
            app.auth_token,
            library.load_library_data,
            favorite_filter,
            album_order,
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

    if not error:
        if app.log_albums:
            app.write_json_log(app.log_albums_path, albums)
        if app.log_artists:
            app.write_json_log(app.log_artists_path, artists)

    GLib.idle_add(
        app.on_library_loaded,
        albums,
        artists,
        error,
    )
    from ui import playlist_manager

    GLib.idle_add(
        playlist_manager.on_playlists_loaded,
        app,
        playlists,
        error,
    )


def on_library_loaded(
    app,
    albums: list[dict],
    artists: list[dict],
    error: str,
) -> None:
    app.library_loading = False
    if app.settings_button:
        app.settings_button.set_sensitive(True)
    app.set_loading_state(False)

    if error:
        app.set_status(error, is_error=True)
        _notify_connection_result(app, error)
        return

    app.set_status("", is_error=False)
    _notify_connection_result(app, error)
    from ui import album_grid

    album_grid.set_album_items(app, albums)
    app.populate_artists_list(artists)

    if app.artists_header:
        app.artists_header.set_label(f"Artists ({len(artists)})")
    if app.current_artist:
        app.refresh_artist_albums()
    app.refresh_output_targets()


def _handle_library_change_refresh(app) -> bool:
    app._library_refresh_source_id = None
    app._library_refresh_pending = False
    app.load_library()
    return False


def set_loading_state(app, loading: bool, message: str = "") -> None:
    if loading:
        if app.library_loading_overlay:
            app.library_loading_overlay.set_visible(True)
        if app.library_loading_spinner:
            app.library_loading_spinner.start()
        if app.library_loading_label:
            app.library_loading_label.set_label("Loading library...")
        if message:
            app.set_status(message, is_error=False)
    else:
        if app.library_loading_spinner:
            app.library_loading_spinner.stop()
        if app.library_loading_overlay:
            app.library_loading_overlay.set_visible(False)

    if app.settings_connect_button:
        app.settings_connect_button.set_sensitive(not loading)
    if getattr(app, "albums_refresh_button", None):
        app.albums_refresh_button.set_sensitive(not loading)
    if getattr(app, "artists_refresh_button", None):
        app.artists_refresh_button.set_sensitive(not loading)


def set_loading_message(app, message: str) -> None:
    if app.library_loading:
        app.set_status(message, is_error=False)
        if app.library_loading_label:
            app.library_loading_label.set_label(message)


def set_status(app, message: str, is_error: bool = False) -> None:
    for label in (app.library_status_label, app.settings_status_label):
        if not label:
            continue
        if is_error:
            label.add_css_class("error")
        else:
            label.remove_css_class("error")
        label.set_label(message)
        label.set_visible(bool(message))


def populate_artists_list(app, artists: list) -> None:
    if not app.artists_list:
        return
    from ui import image_loader, ui_utils

    ui_utils.clear_container(app.artists_list)
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or "Unknown Artist"
        else:
            name = str(artist)
        image_url = (
            image_loader.extract_media_image_url(artist, app.server_url)
            if isinstance(artist, dict)
            else None
        )
        app.artists_list.append(
            ui_utils.make_artist_row(
                name,
                artist,
                image_url=image_url,
                app=app,
            )
        )


def build_artists_section(app) -> Gtk.Widget:
    artists_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

    header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    header_row.set_halign(Gtk.Align.FILL)
    header_row.set_hexpand(True)

    header = Gtk.Label(label="Artists")
    header.add_css_class("artists-header")
    header.set_xalign(0)
    header.set_hexpand(True)
    header.set_halign(Gtk.Align.FILL)
    header_row.append(header)

    refresh_button = Gtk.Button()
    refresh_button.add_css_class("flat")
    refresh_button.set_tooltip_text("Refresh library")
    refresh_button.set_child(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
    refresh_button.connect("clicked", lambda _button: app.load_library())
    refresh_button.set_sensitive(not bool(getattr(app, "library_loading", False)))
    app.artists_refresh_button = refresh_button
    header_row.append(refresh_button)

    app.artists_header = header
    artists_box.append(header_row)

    artists_list = Gtk.ListBox()
    artists_list.add_css_class("artist-list")
    artists_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    artists_list.set_show_separators(True)
    artists_list.set_activate_on_single_click(True)
    artists_list.connect("row-activated", app.on_artist_row_activated)
    app.artists_list = artists_list
    from ui import ui_utils

    populate_artists_list(app, SAMPLE_ARTISTS)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(app.artists_list)
    scroller.set_vexpand(True)

    artists_box.append(scroller)
    return artists_box
