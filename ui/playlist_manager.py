import threading

from gi.repository import Gdk, GLib, Gtk

from music_assistant_client.exceptions import (
    CannotConnect,
    InvalidServerVersion,
    MusicAssistantClientException,
)
from music_assistant_models.errors import AuthenticationFailed, AuthenticationRequired
from music_assistant import library
from ui.sidebar import make_sidebar_row
from ui import ui_utils


def refresh_playlists(app) -> None:
    if not app.playlists_list:
        return
    if app.playlists_loading:
        app.playlists_refresh_pending = True
        return
    if not app.server_url:
        app.playlists_refresh_pending = False
        if app.playlists_add_button:
            app.playlists_add_button.set_sensitive(False)
        populate_playlists_list(app, [])
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to load playlists.",
        )
        return

    if app.playlists_add_button:
        app.playlists_add_button.set_sensitive(True)
    app.playlists_loading = True
    set_playlists_status(app, "Loading playlists...")
    thread = threading.Thread(
        target=load_playlists_worker,
        args=(app,),
        daemon=True,
    )
    thread.start()


def load_playlists_worker(app) -> None:
    error = ""
    playlists: list[dict] = []
    try:
        playlists = app.client_session.run(
            app.server_url,
            app.auth_token,
            load_playlists_async,
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
    GLib.idle_add(on_playlists_loaded, app, playlists, error)


async def load_playlists_async(client) -> list[dict]:
    return await library.fetch_playlists(client)


def on_playlists_loaded(app, playlists: list[dict], error: str) -> None:
    app.playlists_loading = False
    pending_refresh = app.playlists_refresh_pending
    app.playlists_refresh_pending = False
    if error:
        set_playlists_status(
            app,
            f"Unable to load playlists: {error}",
            is_error=True,
        )
        return
    populate_playlists_list(app, playlists)
    if not playlists:
        set_playlists_status(app, "No playlists yet. Click + to create one.")
    else:
        set_playlists_status(app, "")
    if pending_refresh:
        refresh_playlists(app)


def set_playlists_status(app, message: str, is_error: bool = False) -> None:
    if not app.playlists_status_label:
        return
    if is_error:
        app.playlists_status_label.add_css_class("error")
    else:
        app.playlists_status_label.remove_css_class("error")
    app.playlists_status_label.set_label(message)
    app.playlists_status_label.set_visible(bool(message))


def populate_playlists_list(app, playlists: list) -> None:
    if not app.playlists_list:
        return
    app.playlists = playlists or []
    apply_playlist_filter(app)


def on_playlist_filter_changed(app, _entry: Gtk.Entry) -> None:
    apply_playlist_filter(app)


def apply_playlist_filter(app) -> None:
    if not app.playlists_list:
        return
    ui_utils.clear_container(app.playlists_list)
    playlists = app.playlists or []
    filter_text = ""
    filter_entry = getattr(app, "playlists_filter_entry", None)
    if filter_entry:
        filter_text = filter_entry.get_text().strip().casefold()
    for playlist in playlists:
        name = _get_playlist_name(playlist)
        if filter_text and not name.casefold().startswith(filter_text):
            continue
        row = make_sidebar_row(name)
        row.playlist_data = playlist
        _attach_playlist_row_context_menu(app, row)
        app.playlists_list.append(row)


def _attach_playlist_row_context_menu(
    app, row: Gtk.ListBoxRow
) -> None:
    popover = Gtk.Popover()
    popover.set_has_arrow(False)
    popover.add_css_class("track-action-popover")
    action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    action_box.set_margin_start(6)
    action_box.set_margin_end(6)
    action_box.set_margin_top(6)
    action_box.set_margin_bottom(6)
    for action in ("Play", "Add to Queue", "Delete Playlist"):
        action_button = Gtk.Button(label=action)
        action_button.set_halign(Gtk.Align.FILL)
        action_button.set_hexpand(True)
        action_button.add_css_class("track-action-item")
        action_button.connect(
            "clicked",
            app.on_playlist_row_context_action,
            popover,
            action,
            row.playlist_data,
        )
        action_box.append(action_button)
    popover.set_child(action_box)
    ui_utils.attach_context_popover(row, popover)
    gesture = Gtk.GestureClick.new()
    gesture.set_button(3)

    def on_pressed(_gesture, _n_press: int, x: float, y: float) -> None:
        if hasattr(popover, "set_pointing_to"):
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)
        popover.popup()

    gesture.connect("pressed", on_pressed)
    row.add_controller(gesture)


def on_playlist_selected(
    app,
    _listbox: Gtk.ListBox,
    row: Gtk.ListBoxRow | None,
) -> None:
    if not row or not app.main_stack:
        return
    playlist = getattr(row, "playlist_data", None)
    if not playlist:
        return
    app.show_playlist_detail(playlist)
    app.main_stack.set_visible_child_name("playlist-detail")
    if app.home_nav_list:
        app.home_nav_list.unselect_all()
    if app.library_list:
        app.library_list.unselect_all()


def on_playlist_add_clicked(app, _button: Gtk.Button) -> None:
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to create playlists.",
            is_error=True,
        )
        return
    show_create_playlist_dialog(app)


def build_playlist_action_row(app) -> Gtk.Box:
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.START)

    rename_button = Gtk.Button(label="Rename")
    rename_button.set_tooltip_text("Rename playlist")
    rename_button.set_sensitive(False)
    rename_button.connect(
        "clicked", lambda button: on_playlist_rename_clicked(app, button)
    )

    delete_button = Gtk.Button(label="Delete")
    delete_button.add_css_class("destructive-action")
    delete_button.set_tooltip_text("Delete playlist")
    delete_button.set_sensitive(False)
    delete_button.connect(
        "clicked", lambda button: on_playlist_delete_clicked(app, button)
    )

    actions.append(rename_button)
    actions.append(delete_button)

    app.playlist_detail_rename_button = rename_button
    app.playlist_detail_delete_button = delete_button
    return actions


def on_playlist_rename_clicked(app, _button: Gtk.Button) -> None:
    playlist = app.current_playlist
    if not playlist:
        set_playlists_status(app, "No playlist selected.", is_error=True)
        return
    show_rename_playlist_dialog(app, playlist)


def on_playlist_delete_clicked(app, _button: Gtk.Button) -> None:
    playlist = app.current_playlist
    if not playlist:
        set_playlists_status(app, "No playlist selected.", is_error=True)
        return
    show_delete_playlist_dialog(app, playlist)


def show_create_playlist_dialog(app, track=None) -> None:
    if not app.window:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to create playlists.",
            is_error=True,
        )
        return
    dialog = Gtk.Window(application=app, transient_for=app.window, modal=True)
    dialog.set_title("New Playlist")
    dialog.set_default_size(360, -1)
    dialog.set_resizable(False)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content.set_margin_top(16)
    content.set_margin_bottom(16)
    content.set_margin_start(16)
    content.set_margin_end(16)

    name_label = Gtk.Label(label="Playlist name", xalign=0)
    name_entry = Gtk.Entry()
    name_entry.set_placeholder_text("New playlist")
    name_entry.set_hexpand(True)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    cancel_button = Gtk.Button(label="Cancel")
    create_button = Gtk.Button(label="Create")
    create_button.add_css_class("suggested-action")
    create_button.set_sensitive(False)
    actions.append(cancel_button)
    actions.append(create_button)

    content.append(name_label)
    content.append(name_entry)
    content.append(actions)
    dialog.set_child(content)

    def update_create_state(*_args: object) -> None:
        create_button.set_sensitive(bool(name_entry.get_text().strip()))

    def close_dialog(*_args: object) -> None:
        dialog.close()

    def submit_dialog(*_args: object) -> None:
        name = name_entry.get_text().strip()
        if not name:
            return
        dialog.close()
        create_playlist(app, name, track)

    name_entry.connect("changed", update_create_state)
    name_entry.connect("activate", submit_dialog)
    cancel_button.connect("clicked", close_dialog)
    create_button.connect("clicked", submit_dialog)

    update_create_state()
    dialog.present()
    name_entry.grab_focus()


def create_playlist(app, name: str, track=None) -> None:
    cleaned = name.strip()
    if not cleaned:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to create playlists.",
            is_error=True,
        )
        return
    set_playlists_status(app, "Creating playlist...")
    thread = threading.Thread(
        target=create_playlist_worker,
        args=(app, cleaned, track),
        daemon=True,
    )
    thread.start()


def create_playlist_worker(app, name: str, track) -> None:
    error = ""
    playlist = None
    try:
        playlist = app.client_session.run(
            app.server_url,
            app.auth_token,
            library.create_playlist,
            name,
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
    GLib.idle_add(on_playlist_created, app, playlist, error, track)


def on_playlist_created(app, playlist: object, error: str, track) -> None:
    if error:
        set_playlists_status(
            app,
            f"Unable to create playlist: {error}",
            is_error=True,
        )
        return
    refresh_playlists(app)
    if track and playlist:
        add_track_to_playlist(app, track, playlist)


def show_rename_playlist_dialog(app, playlist: object) -> None:
    if not app.window:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    if not _is_editable_playlist(playlist):
        set_playlists_status(
            app,
            "This playlist cannot be edited.",
            is_error=True,
        )
        return
    current_name = _get_playlist_name(playlist)

    dialog = Gtk.Window(application=app, transient_for=app.window, modal=True)
    dialog.set_title("Rename Playlist")
    dialog.set_default_size(360, -1)
    dialog.set_resizable(False)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content.set_margin_top(16)
    content.set_margin_bottom(16)
    content.set_margin_start(16)
    content.set_margin_end(16)

    name_label = Gtk.Label(label="Playlist name", xalign=0)
    name_entry = Gtk.Entry()
    name_entry.set_text(current_name)
    name_entry.set_hexpand(True)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    cancel_button = Gtk.Button(label="Cancel")
    rename_button = Gtk.Button(label="Rename")
    rename_button.add_css_class("suggested-action")
    rename_button.set_sensitive(False)
    actions.append(cancel_button)
    actions.append(rename_button)

    content.append(name_label)
    content.append(name_entry)
    content.append(actions)
    dialog.set_child(content)

    def update_rename_state(*_args: object) -> None:
        cleaned = name_entry.get_text().strip()
        rename_button.set_sensitive(bool(cleaned) and cleaned != current_name)

    def close_dialog(*_args: object) -> None:
        dialog.close()

    def submit_dialog(*_args: object) -> None:
        name = name_entry.get_text().strip()
        if not name or name == current_name:
            dialog.close()
            return
        dialog.close()
        rename_playlist(app, playlist, name)

    name_entry.connect("changed", update_rename_state)
    name_entry.connect("activate", submit_dialog)
    cancel_button.connect("clicked", close_dialog)
    rename_button.connect("clicked", submit_dialog)

    update_rename_state()
    dialog.present()
    name_entry.grab_focus()
    name_entry.select_region(0, -1)


def rename_playlist(app, playlist: object, name: str) -> None:
    cleaned = name.strip()
    if not cleaned:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    if not _is_editable_playlist(playlist):
        set_playlists_status(
            app,
            "This playlist cannot be edited.",
            is_error=True,
        )
        return
    playlist_id = _get_playlist_id(playlist)
    if not playlist_id:
        set_playlists_status(
            app,
            "Unable to rename playlist: missing playlist ID.",
            is_error=True,
        )
        return
    provider = _get_playlist_provider(playlist)
    if not provider:
        set_playlists_status(
            app,
            "Unable to rename playlist: missing playlist provider.",
            is_error=True,
        )
        return
    playlist_name = _get_playlist_name(playlist)
    set_playlists_status(app, f"Renaming {playlist_name}...")
    thread = threading.Thread(
        target=rename_playlist_worker,
        args=(app, playlist_id, provider, playlist_name, cleaned),
        daemon=True,
    )
    thread.start()


def rename_playlist_worker(
    app,
    playlist_id: str | int,
    provider: str,
    playlist_name: str,
    new_name: str,
) -> None:
    error = ""
    updated = None
    try:
        updated = app.client_session.run(
            app.server_url,
            app.auth_token,
            library.rename_playlist,
            playlist_id,
            provider,
            new_name,
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
        on_playlist_renamed,
        app,
        playlist_id,
        playlist_name,
        new_name,
        updated,
        error,
    )


def on_playlist_renamed(
    app,
    playlist_id: str | int,
    playlist_name: str,
    new_name: str,
    updated: object,
    error: str,
) -> None:
    if error:
        set_playlists_status(
            app,
            f"Unable to rename playlist: {error}",
            is_error=True,
        )
        return
    refresh_playlists(app)
    set_playlists_status(app, f"Renamed {playlist_name} to {new_name}.")
    current = app.current_playlist
    if current and _playlist_id_matches(current, playlist_id):
        updated_payload = None
        if updated:
            try:
                updated_payload = library._serialize_playlist(updated)
            except Exception:
                updated_payload = None
        if updated_payload:
            app.current_playlist = updated_payload
            app.current_album = updated_payload
            if app.playlist_detail_title:
                app.playlist_detail_title.set_label(
                    _get_playlist_name(updated_payload)
                )
            new_id = _get_playlist_id(updated_payload)
            if new_id is not None and str(new_id) != str(playlist_id):
                app.load_playlist_tracks(updated_payload)


def show_delete_playlist_dialog(app, playlist: object) -> None:
    if not app.window:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    if not _is_editable_playlist(playlist):
        set_playlists_status(
            app,
            "This playlist cannot be edited.",
            is_error=True,
        )
        return
    playlist_name = _get_playlist_name(playlist)

    dialog = Gtk.Window(application=app, transient_for=app.window, modal=True)
    dialog.set_title("Delete Playlist")
    dialog.set_default_size(360, -1)
    dialog.set_resizable(False)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content.set_margin_top(16)
    content.set_margin_bottom(16)
    content.set_margin_start(16)
    content.set_margin_end(16)

    message = Gtk.Label(
        label=f'Delete "{playlist_name}"? This cannot be undone.',
        xalign=0,
    )
    message.set_wrap(True)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    cancel_button = Gtk.Button(label="Cancel")
    delete_button = Gtk.Button(label="Delete")
    delete_button.add_css_class("destructive-action")
    actions.append(cancel_button)
    actions.append(delete_button)

    content.append(message)
    content.append(actions)
    dialog.set_child(content)

    def close_dialog(*_args: object) -> None:
        dialog.close()

    def submit_dialog(*_args: object) -> None:
        dialog.close()
        delete_playlist(app, playlist)

    cancel_button.connect("clicked", close_dialog)
    delete_button.connect("clicked", submit_dialog)

    dialog.present()


def delete_playlist(app, playlist: object) -> None:
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    if not _is_editable_playlist(playlist):
        set_playlists_status(
            app,
            "This playlist cannot be edited.",
            is_error=True,
        )
        return
    playlist_id = _get_playlist_id(playlist)
    if not playlist_id:
        set_playlists_status(
            app,
            "Unable to delete playlist: missing playlist ID.",
            is_error=True,
        )
        return
    playlist_name = _get_playlist_name(playlist)
    set_playlists_status(app, f"Deleting {playlist_name}...")
    thread = threading.Thread(
        target=delete_playlist_worker,
        args=(app, playlist_id, playlist_name),
        daemon=True,
    )
    thread.start()


def delete_playlist_worker(
    app, playlist_id: str | int, playlist_name: str
) -> None:
    error = ""
    try:
        app.client_session.run(
            app.server_url,
            app.auth_token,
            library.delete_playlist,
            playlist_id,
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
        on_playlist_deleted,
        app,
        playlist_id,
        playlist_name,
        error,
    )


def on_playlist_deleted(
    app, playlist_id: str | int, playlist_name: str, error: str
) -> None:
    if error:
        set_playlists_status(
            app,
            f"Unable to delete playlist: {error}",
            is_error=True,
        )
        return
    refresh_playlists(app)
    set_playlists_status(app, f"Deleted {playlist_name}.")
    current = app.current_playlist
    if current and _playlist_id_matches(current, playlist_id):
        _close_playlist_detail_view(app)


def _close_playlist_detail_view(app) -> None:
    app.current_playlist = None
    app.current_album = None
    app.current_album_tracks = []
    if app.main_stack:
        app.main_stack.set_visible_child_name("home")
    if app.playlists_list:
        app.playlists_list.unselect_all()
    if app.home_nav_list:
        app.home_nav_list.unselect_all()
    if app.library_list:
        app.library_list.unselect_all()
    if app.playlist_detail_title:
        app.playlist_detail_title.set_label("Playlist")
    if hasattr(app, "set_playlist_detail_status"):
        app.set_playlist_detail_status("")


def show_add_to_playlist_dialog(app, track) -> None:
    if not app.window:
        return
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    track_uris = _get_track_uris(track)
    if not track_uris:
        set_playlists_status(
            app,
            "Unable to add track: missing track URI.",
            is_error=True,
        )
        return
    playlists = [
        playlist
        for playlist in (app.playlists or [])
        if _is_editable_playlist(playlist)
    ]
    if not playlists:
        set_playlists_status(
            app,
            "No editable playlists available. Create one first.",
            is_error=True,
        )
        return

    dialog = Gtk.Window(application=app, transient_for=app.window, modal=True)
    dialog.set_title("Add to Playlist")
    dialog.set_default_size(360, -1)
    dialog.set_resizable(False)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    content.set_margin_top(16)
    content.set_margin_bottom(16)
    content.set_margin_start(16)
    content.set_margin_end(16)

    playlist_label = Gtk.Label(label="Select playlist", xalign=0)
    names = [_get_playlist_name(item) for item in playlists]
    playlist_list = Gtk.StringList.new(names)
    playlist_picker = Gtk.DropDown.new(playlist_list, None)
    playlist_picker.set_hexpand(True)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.END)
    cancel_button = Gtk.Button(label="Cancel")
    add_button = Gtk.Button(label="Add")
    add_button.add_css_class("suggested-action")
    actions.append(cancel_button)
    actions.append(add_button)

    content.append(playlist_label)
    content.append(playlist_picker)
    content.append(actions)
    dialog.set_child(content)

    def close_dialog(*_args: object) -> None:
        dialog.close()

    def submit_dialog(*_args: object) -> None:
        index = playlist_picker.get_selected()
        if index < 0 or index >= len(playlists):
            return
        dialog.close()
        add_tracks_to_playlist(app, track_uris, playlists[index])

    cancel_button.connect("clicked", close_dialog)
    add_button.connect("clicked", submit_dialog)

    dialog.present()


def add_track_to_playlist(app, track, playlist: dict) -> None:
    track_uris = _get_track_uris(track)
    if not track_uris:
        set_playlists_status(
            app,
            "Unable to add track: missing track URI.",
            is_error=True,
        )
        return
    add_tracks_to_playlist(app, track_uris, playlist)


def add_tracks_to_playlist(
    app,
    track_uris: list[str],
    playlist: dict,
) -> None:
    if not app.server_url:
        set_playlists_status(
            app,
            "Connect to your Music Assistant server to edit playlists.",
            is_error=True,
        )
        return
    if not track_uris:
        set_playlists_status(
            app,
            "Unable to add track: missing track URI.",
            is_error=True,
        )
        return
    playlist_id = _get_playlist_id(playlist)
    if not playlist_id:
        set_playlists_status(
            app,
            "Unable to add track: missing playlist ID.",
            is_error=True,
        )
        return
    playlist_name = _get_playlist_name(playlist)
    track_count = len(track_uris)
    noun = "track" if track_count == 1 else "tracks"
    set_playlists_status(
        app,
        f"Adding {track_count} {noun} to {playlist_name}...",
    )
    thread = threading.Thread(
        target=add_tracks_to_playlist_worker,
        args=(app, playlist_id, playlist_name, list(track_uris)),
        daemon=True,
    )
    thread.start()


def add_tracks_to_playlist_worker(
    app,
    playlist_id: str | int,
    playlist_name: str,
    track_uris: list[str],
) -> None:
    error = ""
    try:
        app.client_session.run(
            app.server_url,
            app.auth_token,
            _add_tracks_to_playlist_async,
            playlist_id,
            track_uris,
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
        on_tracks_added_to_playlist,
        app,
        playlist_id,
        playlist_name,
        len(track_uris),
        error,
    )


async def _add_tracks_to_playlist_async(
    client,
    playlist_id: str | int,
    track_uris: list[str],
) -> None:
    if not track_uris:
        return
    await client.music.add_playlist_tracks(playlist_id, track_uris)


def on_tracks_added_to_playlist(
    app,
    playlist_id: str | int,
    playlist_name: str,
    track_count: int,
    error: str,
) -> None:
    if error:
        set_playlists_status(
            app,
            f"Unable to add track: {error}",
            is_error=True,
        )
        return
    noun = "track" if track_count == 1 else "tracks"
    set_playlists_status(
        app,
        f"Added {track_count} {noun} to {playlist_name}.",
    )
    current = app.current_playlist
    if current and _playlist_id_matches(current, playlist_id):
        app.load_playlist_tracks(current, force_refresh=True)


def _get_track_uri(track) -> str | None:
    source = getattr(track, "source", None)
    return getattr(source, "uri", None) if source else None


def _get_track_uris(track_or_tracks) -> list[str]:
    if track_or_tracks is None:
        return []
    if isinstance(track_or_tracks, (list, tuple, set)):
        track_items = list(track_or_tracks)
    else:
        track_items = [track_or_tracks]
    uris: list[str] = []
    seen: set[str] = set()
    for item in track_items:
        uri = _get_track_uri(item)
        if isinstance(uri, str):
            uri = uri.strip()
        else:
            uri = None
        if not uri or uri in seen:
            continue
        seen.add(uri)
        uris.append(uri)
    return uris


def _get_playlist_name(playlist: object) -> str:
    if isinstance(playlist, dict):
        return playlist.get("name") or "Untitled Playlist"
    return getattr(playlist, "name", None) or "Untitled Playlist"


def _get_playlist_id(playlist: object) -> str | int | None:
    if isinstance(playlist, dict):
        return playlist.get("item_id") or playlist.get("id")
    return getattr(playlist, "item_id", None)


def _get_playlist_provider(playlist: object) -> str | None:
    if isinstance(playlist, dict):
        return playlist.get("provider")
    return getattr(playlist, "provider", None)


def _playlist_id_matches(playlist: object, playlist_id: str | int) -> bool:
    current_id = _get_playlist_id(playlist)
    if current_id is None:
        return False
    return str(current_id) == str(playlist_id)


def _is_editable_playlist(playlist: object) -> bool:
    if isinstance(playlist, dict):
        return bool(playlist.get("is_editable", False))
    return bool(getattr(playlist, "is_editable", False))
