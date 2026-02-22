"""Queue panel UI and queue interaction helpers."""

import logging
import threading

from gi.repository import GLib, Gtk, Pango

from constants import TRACK_ART_SIZE
from music_assistant import playback
from ui import image_loader, ui_utils


def build_queue_panel(app) -> Gtk.Widget:
    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    container.add_css_class("search-section-content")
    container.set_hexpand(True)
    container.set_vexpand(True)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    card.add_css_class("search-group")
    card.set_hexpand(True)
    card.set_vexpand(True)

    header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    header_row.set_hexpand(True)
    header_row.set_halign(Gtk.Align.FILL)

    title = Gtk.Label(label="Up Next")
    title.add_css_class("section-title")
    title.set_xalign(0)
    title.set_hexpand(True)
    header_row.append(title)

    clear_button = Gtk.Button(label="Clear Queue")
    clear_button.connect("clicked", app.on_queue_clear_clicked)
    header_row.append(clear_button)

    close_button = Gtk.Button()
    close_button.add_css_class("flat")
    close_button.set_tooltip_text("Close queue")
    close_button.set_child(Gtk.Image.new_from_icon_name("window-close-symbolic"))
    close_button.connect("clicked", app.on_queue_panel_close_clicked)
    header_row.append(close_button)
    card.append(header_row)

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    card.append(status)

    queue_list = Gtk.ListBox()
    queue_list.add_css_class("artist-list")
    queue_list.add_css_class("queue-list")
    queue_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    queue_list.set_activate_on_single_click(True)
    queue_list.connect("row-activated", app.on_queue_row_activated)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    scroller.set_child(queue_list)
    card.append(scroller)

    close_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    close_row.set_halign(Gtk.Align.END)
    close_button = Gtk.Button(label="Close")
    close_button.connect("clicked", app.on_queue_panel_close_clicked)
    close_row.append(close_button)
    card.append(close_row)

    container.append(card)
    app.queue_list = queue_list
    app.queue_panel_view = container
    app.queue_status_label = status
    app.queue_clear_button = clear_button
    return container


def on_queue_button_clicked(app, _button: Gtk.Button | None = None) -> None:
    if not app.main_stack:
        return
    try:
        current_view = app.main_stack.get_visible_child_name()
    except Exception:
        current_view = None
    if current_view == "queue":
        app.on_queue_panel_close_clicked()
        return
    if current_view and current_view != "queue":
        app.queue_previous_view = current_view
    app.main_stack.set_visible_child_name("queue")
    app.refresh_queue_panel()


def on_queue_panel_close_clicked(app, _button: Gtk.Button | None = None) -> None:
    target_view = getattr(app, "queue_previous_view", None) or "home"
    if app.main_stack:
        app.main_stack.set_visible_child_name(target_view)


def on_queue_clear_clicked(app, _button: Gtk.Button | None = None) -> None:
    if not app.server_url:
        _set_queue_status(
            app,
            "Connect to your Music Assistant server to load the queue.",
        )
        return
    if getattr(app, "queue_clearing", False):
        return
    app.queue_clearing = True
    _set_queue_clear_button_sensitive(app, False)
    _set_queue_status(app, "Clearing queue...")
    thread = threading.Thread(
        target=_clear_queue_worker,
        args=(
            app,
            app.output_manager.preferred_player_id if app.output_manager else None,
        ),
        daemon=True,
    )
    thread.start()


def refresh_queue_panel(app) -> None:
    if not app.queue_list:
        return
    if not app.server_url:
        _set_queue_status(
            app,
            "Connect to your Music Assistant server to load the queue.",
        )
        ui_utils.clear_container(app.queue_list)
        return
    if getattr(app, "queue_loading", False):
        return
    app.queue_loading = True
    _set_queue_status(app, "Loading queue...")
    thread = threading.Thread(
        target=app._load_queue_panel_worker,
        daemon=True,
    )
    thread.start()


def _load_queue_panel_worker(app) -> None:
    error = ""
    items: list[dict] = []
    try:
        items = playback.fetch_queue_items(
            app.client_session,
            app.server_url,
            app.auth_token,
            app.output_manager.preferred_player_id if app.output_manager else None,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_queue_items_loaded, items, error)


def on_queue_items_loaded(app, items: list[dict], error: str) -> None:
    app.queue_loading = False
    if not app.queue_list:
        return
    operation_error = getattr(app, "queue_operation_error", "")
    app.queue_operation_error = ""
    ui_utils.clear_container(app.queue_list)
    if error:
        _set_queue_status(app, f"Unable to load queue: {error}")
        return
    total_items = len(items)
    if operation_error:
        _set_queue_status(app, operation_error)
    if not items:
        if not operation_error:
            _set_queue_status(app, "Queue is empty.")
        return
    for index, item in enumerate(items):
        row = _make_queue_row(
            app,
            item,
            can_move_up=index > 0,
            can_move_down=index < (total_items - 1),
        )
        app.queue_list.append(row)
    if not operation_error:
        _set_queue_status(app, "")


def on_queue_row_activated(
    app,
    _listbox: Gtk.ListBox,
    row: Gtk.ListBoxRow | None,
) -> None:
    if row is None:
        return
    index = getattr(row, "queue_index", None)
    if index is None:
        return
    app.send_playback_index(int(index))


def on_queue_item_remove_clicked(
    app,
    _button: Gtk.Button,
    queue_item_id: str | int | None,
) -> None:
    if not queue_item_id:
        return
    thread = threading.Thread(
        target=_delete_queue_item_worker,
        args=(app, str(queue_item_id)),
        daemon=True,
    )
    thread.start()


def on_queue_item_move_clicked(
    app,
    _button: Gtk.Button,
    queue_item_id: str | int | None,
    pos_shift: int,
) -> None:
    if not queue_item_id:
        return
    shift = int(pos_shift)
    if shift == 0:
        return
    _set_queue_status(app, "Updating queue order...")
    thread = threading.Thread(
        target=_move_queue_item_worker,
        args=(app, str(queue_item_id), shift),
        daemon=True,
    )
    thread.start()


def _delete_queue_item_worker(app, queue_item_id: str) -> None:
    error = ""
    try:
        playback.delete_queue_item(
            app.client_session,
            app.server_url,
            app.auth_token,
            app.output_manager.preferred_player_id if app.output_manager else None,
            queue_item_id,
        )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "Unable to remove queue item %s: %s",
            queue_item_id,
            error,
        )
    GLib.idle_add(app.refresh_queue_panel)


def _move_queue_item_worker(
    app,
    queue_item_id: str,
    pos_shift: int,
) -> None:
    error = ""
    try:
        playback.move_queue_item(
            app.client_session,
            app.server_url,
            app.auth_token,
            app.output_manager.preferred_player_id if app.output_manager else None,
            queue_item_id,
            int(pos_shift),
        )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "Unable to move queue item %s: %s",
            queue_item_id,
            error,
        )
        app.queue_operation_error = f"Unable to reorder queue: {error}"
    GLib.idle_add(app.refresh_queue_panel)


def _clear_queue_worker(app, preferred_player_id: str | None) -> None:
    error = ""
    try:
        playback.clear_queue(
            app.client_session,
            app.server_url,
            app.auth_token,
            preferred_player_id,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(_on_queue_cleared, app, error)


def _on_queue_cleared(app, error: str) -> bool:
    app.queue_clearing = False
    _set_queue_clear_button_sensitive(app, True)
    if error:
        logging.getLogger(__name__).warning("Unable to clear queue: %s", error)
        app.queue_operation_error = f"Unable to clear queue: {error}"
    else:
        app.queue_operation_error = ""
    app.refresh_queue_panel()
    return False


def _make_queue_row(
    app,
    item: dict,
    *,
    can_move_up: bool,
    can_move_down: bool,
) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row.queue_index = int(item.get("index", 0))
    row.queue_item_id = item.get("item_id")

    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    content.set_margin_start(8)
    content.set_margin_end(8)
    content.set_margin_top(6)
    content.set_margin_bottom(6)

    art = Gtk.Picture()
    art.add_css_class("track-art")
    art.add_css_class("queue-art")
    art.set_size_request(TRACK_ART_SIZE, TRACK_ART_SIZE)
    art.set_halign(Gtk.Align.START)
    art.set_valign(Gtk.Align.CENTER)
    art.set_can_shrink(True)
    if hasattr(art, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        art.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(art, "set_keep_aspect_ratio"):
        art.set_keep_aspect_ratio(False)
    _load_queue_item_art(app, art, item)

    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    labels.set_hexpand(True)

    title = Gtk.Label(label=item.get("title") or "Unknown Track")
    title.set_xalign(0)
    title.set_hexpand(True)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    labels.append(title)

    artist = item.get("artist") or "Unknown Artist"
    duration_seconds = item.get("duration") or 0
    subtitle_text = artist
    if duration_seconds:
        minutes, seconds = divmod(int(duration_seconds), 60)
        subtitle_text = f"{artist}  {minutes}:{seconds:02d}"
    subtitle = Gtk.Label(label=subtitle_text)
    subtitle.add_css_class("status-label")
    subtitle.set_xalign(0)
    subtitle.set_ellipsize(Pango.EllipsizeMode.END)
    labels.append(subtitle)

    move_buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    move_buttons.set_valign(Gtk.Align.CENTER)

    move_up_button = Gtk.Button()
    move_up_button.add_css_class("flat")
    move_up_button.set_tooltip_text("Move up")
    move_up_button.set_child(Gtk.Image.new_from_icon_name("go-up-symbolic"))
    move_up_button.set_sensitive(can_move_up)
    move_up_button.connect(
        "clicked",
        app.on_queue_item_move_clicked,
        row.queue_item_id,
        -1,
    )

    move_down_button = Gtk.Button()
    move_down_button.add_css_class("flat")
    move_down_button.set_tooltip_text("Move down")
    move_down_button.set_child(Gtk.Image.new_from_icon_name("go-down-symbolic"))
    move_down_button.set_sensitive(can_move_down)
    move_down_button.connect(
        "clicked",
        app.on_queue_item_move_clicked,
        row.queue_item_id,
        1,
    )

    remove_button = Gtk.Button()
    remove_button.add_css_class("flat")
    remove_button.set_tooltip_text("Remove from queue")
    remove_button.set_child(Gtk.Image.new_from_icon_name("list-remove-symbolic"))
    remove_button.connect(
        "clicked",
        app.on_queue_item_remove_clicked,
        row.queue_item_id,
    )

    content.append(art)
    content.append(labels)
    move_buttons.append(move_up_button)
    move_buttons.append(move_down_button)
    content.append(move_buttons)
    content.append(remove_button)
    row.set_child(content)

    if _is_current_queue_item(app, item):
        row.add_css_class("queue-current-item")
    return row


def _load_queue_item_art(app, picture: Gtk.Picture, item: dict) -> None:
    image_url = item.get("image_url")
    if isinstance(image_url, str):
        normalized = image_url.strip()
        image_url = normalized if normalized else None
    else:
        image_url = None
    if image_url:
        resolved = image_loader.resolve_image_url(image_url, app.server_url)
        image_url = resolved or image_url
    if not image_url:
        picture.set_paintable(None)
        try:
            picture.expected_image_url = None
        except Exception:
            pass
        return
    picture.set_paintable(None)
    image_loader.load_album_art_async(
        picture,
        image_url,
        TRACK_ART_SIZE,
        app.auth_token,
        app.image_executor,
        app.get_cache_dir(),
    )


def _is_current_queue_item(app, item: dict) -> bool:
    track_info = getattr(app, "playback_track_info", None) or {}
    source_uri = track_info.get("source_uri")
    queue_uri = item.get("uri")
    if source_uri and queue_uri:
        return str(source_uri) == str(queue_uri)
    index = item.get("index")
    playing_index = getattr(app, "playback_track_index", None)
    if playing_index is None or index is None:
        return False
    return int(index) == int(playing_index)


def _set_queue_status(app, message: str) -> None:
    if not getattr(app, "queue_status_label", None):
        return
    app.queue_status_label.set_label(message)
    app.queue_status_label.set_visible(bool(message))


def _set_queue_clear_button_sensitive(app, sensitive: bool) -> None:
    button = getattr(app, "queue_clear_button", None)
    if button is None:
        return
    button.set_sensitive(bool(sensitive))
