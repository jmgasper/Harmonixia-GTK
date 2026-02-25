"""Queue panel UI and queue interaction helpers."""

import logging
import threading

from gi.repository import Gdk, GLib, GObject, Gtk, Pango

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

    transfer_button = Gtk.MenuButton(label="Transfer to…")
    transfer_button.add_css_class("queue-transfer-button")

    transfer_popover = Gtk.Popover()
    transfer_popover.set_has_arrow(False)
    transfer_popover.set_position(Gtk.PositionType.BOTTOM)
    transfer_popover.connect("map", app.on_queue_transfer_popover_mapped)

    transfer_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    transfer_container.set_margin_start(6)
    transfer_container.set_margin_end(6)
    transfer_container.set_margin_top(6)
    transfer_container.set_margin_bottom(6)

    transfer_title = Gtk.Label(label="Transfer queue to", xalign=0)
    transfer_title.add_css_class("output-title")
    transfer_container.append(transfer_title)

    transfer_list = Gtk.ListBox()
    transfer_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    transfer_list.set_activate_on_single_click(True)
    transfer_list.add_css_class("output-list")
    transfer_list.connect("row-activated", app.on_queue_transfer_row_activated)
    transfer_container.append(transfer_list)

    transfer_status = Gtk.Label()
    transfer_status.add_css_class("status-label")
    transfer_status.set_xalign(0)
    transfer_status.set_wrap(True)
    transfer_status.set_visible(False)
    transfer_container.append(transfer_status)

    transfer_popover.set_child(transfer_container)
    transfer_button.set_popover(transfer_popover)
    header_row.append(transfer_button)

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
    app.queue_transfer_button = transfer_button
    app.queue_transfer_list = transfer_list
    app.queue_transfer_status = transfer_status
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


def on_queue_transfer_popover_mapped(app, _popover: Gtk.Popover) -> None:
    listbox = getattr(app, "queue_transfer_list", None)
    if listbox is None:
        return
    ui_utils.clear_container(listbox)
    outputs = app.output_manager.get_output_targets() if app.output_manager else []
    preferred_player_id = (
        app.output_manager.preferred_player_id if app.output_manager else None
    )
    rows_added = 0
    for output in outputs:
        player_id = output.get("player_id")
        if not player_id or player_id == preferred_player_id:
            continue
        row = Gtk.ListBoxRow()
        row.player_id = player_id
        label = Gtk.Label(label=output.get("display_name") or "", xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_margin_top(2)
        label.set_margin_bottom(2)
        row.set_child(label)
        listbox.append(row)
        rows_added += 1
    status = getattr(app, "queue_transfer_status", None)
    if status is not None:
        if rows_added == 0:
            status.set_label("No other players available.")
            status.set_visible(True)
        else:
            status.set_label("")
            status.set_visible(False)


def on_queue_transfer_row_activated(
    app,
    _listbox: Gtk.ListBox,
    row: Gtk.ListBoxRow | None,
) -> None:
    if row is None:
        return
    if app.queue_transfer_button:
        popover = app.queue_transfer_button.get_popover()
        if popover:
            popover.popdown()
    app.on_queue_transfer_clicked(getattr(row, "player_id", None))


def on_queue_transfer_clicked(app, target_player_id: str | None) -> None:
    if not app.server_url or not target_player_id:
        return
    if getattr(app, "queue_transferring", False):
        return
    app.queue_transferring = True
    _set_queue_status(app, "Transferring queue...")
    thread = threading.Thread(
        target=_queue_transfer_worker,
        args=(
            app,
            app.output_manager.preferred_player_id if app.output_manager else None,
            target_player_id,
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
    if operation_error:
        _set_queue_status(app, operation_error)
    if not items:
        if not operation_error:
            _set_queue_status(app, "Queue is empty.")
        return
    for item in items:
        row = _make_queue_row(
            app,
            item,
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


def _queue_transfer_worker(
    app,
    source_player_id: str | None,
    target_player_id: str | None,
) -> None:
    error = ""
    try:
        playback.transfer_queue(
            app.client_session,
            app.server_url,
            app.auth_token,
            source_player_id,
            target_player_id,
            auto_play=None,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(_on_queue_transferred, app, error)


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


def _on_queue_transferred(app, error: str) -> bool:
    app.queue_transferring = False
    if error:
        logging.getLogger(__name__).warning("Unable to transfer queue: %s", error)
        _set_queue_status(app, f"Transfer failed: {error}")
    else:
        _set_queue_status(app, "Queue transferred.")
    return False


def _make_queue_row(
    app,
    item: dict,
) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row.queue_index = int(item.get("index", 0))
    row.queue_item_id = item.get("item_id")

    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    content.set_margin_start(8)
    content.set_margin_end(8)
    content.set_margin_top(6)
    content.set_margin_bottom(6)

    drag_handle = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
    drag_handle.add_css_class("queue-drag-handle")
    drag_handle.set_valign(Gtk.Align.CENTER)

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

    remove_button = Gtk.Button()
    remove_button.add_css_class("flat")
    remove_button.set_tooltip_text("Remove from queue")
    remove_button.set_child(Gtk.Image.new_from_icon_name("list-remove-symbolic"))
    remove_button.connect(
        "clicked",
        app.on_queue_item_remove_clicked,
        row.queue_item_id,
    )

    content.append(drag_handle)
    content.append(art)
    content.append(labels)
    content.append(remove_button)
    row.set_child(content)

    drag_source = Gtk.DragSource.new()
    drag_source.set_actions(Gdk.DragAction.MOVE)

    def on_drag_prepare(_source, _x, _y):
        return Gdk.ContentProvider.new_for_value(
            f"{row.queue_item_id}:{row.queue_index}",
        )

    drag_source.connect("prepare", on_drag_prepare)
    row.add_controller(drag_source)

    drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)

    def on_drop(_target, value, _x, _y):
        if not isinstance(value, str) or ":" not in value:
            row.remove_css_class("queue-drop-target")
            return False

        source_item_id, source_index = value.split(":", 1)
        if not source_item_id:
            row.remove_css_class("queue-drop-target")
            return False
        try:
            pos_shift = row.queue_index - int(source_index)
        except (TypeError, ValueError):
            row.remove_css_class("queue-drop-target")
            return False
        if pos_shift == 0:
            row.remove_css_class("queue-drop-target")
            return False

        app.on_queue_item_move_clicked(None, source_item_id, pos_shift)
        row.remove_css_class("queue-drop-target")
        return True

    def on_motion(_target, _x, _y):
        row.add_css_class("queue-drop-target")
        return Gdk.DragAction.MOVE

    def on_leave(_target):
        row.remove_css_class("queue-drop-target")

    drop_target.connect("drop", on_drop)
    drop_target.connect("motion", on_motion)
    drop_target.connect("leave", on_leave)
    row.add_controller(drop_target)

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
