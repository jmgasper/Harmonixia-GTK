"""Output selection and Sendspin event handlers."""

import logging
import os
import threading

from gi.repository import GLib, Gtk, Pango

from music_assistant import playback, sendspin
from music_assistant_models.enums import PlaybackState
from ui import ui_utils


def on_output_popover_mapped(app, _popover: Gtk.Popover) -> None:
    app.sendspin_manager.start(app.server_url)
    app.output_manager.refresh()


def on_output_target_activated(app, _listbox: Gtk.ListBox, row) -> None:
    if app.suppress_output_selection or row is None:
        return
    previous = app.output_manager.get_selected_output()
    previous_player_id = previous.get("player_id") if previous else None
    previous_local_output_id = (
        previous.get("local_output_id") if previous else None
    )
    player_id = getattr(row, "player_id", None)
    local_output_id = getattr(row, "local_output_id", None)
    if not player_id:
        return
    selection_changed = (
        previous_player_id,
        previous_local_output_id,
    ) != (player_id, local_output_id)
    app.output_manager.select_output(player_id, local_output_id)
    if app.output_popover:
        app.output_popover.popdown()
    if selection_changed:
        _maybe_transfer_output(
            app,
            previous_player_id,
            player_id,
        )


def on_outputs_changed(app) -> None:
    GLib.idle_add(app._apply_outputs_changed)


def _apply_outputs_changed(app) -> None:
    if app.output_targets_list is None:
        return
    ui_utils.clear_container(app.output_targets_list)
    app.output_target_rows = {}
    outputs = app.output_manager.get_output_targets()
    selected = app.output_manager.get_selected_output()
    unique_outputs = []
    seen = {}
    index_by_key = {}
    for output in outputs:
        display_name = (output.get("display_name") or "").strip()
        key = display_name.casefold()
        if key in seen:
            continue
        seen[key] = output
        index_by_key[key] = len(unique_outputs)
        unique_outputs.append(output)
    if selected:
        selected_name = (selected.get("display_name") or "").strip()
        selected_key = selected_name.casefold()
        index = index_by_key.get(selected_key)
        if index is None:
            index_by_key[selected_key] = 0
            unique_outputs.insert(0, selected)
        elif unique_outputs[index] is not selected:
            unique_outputs[index] = selected
            seen[selected_key] = selected
    for output in unique_outputs:
        row = Gtk.ListBoxRow()
        row.player_id = output["player_id"]
        row.local_output_id = output["local_output_id"]
        row.local_output_name = output["local_output_name"]
        label = Gtk.Label(label=output["display_name"], xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_margin_top(2)
        label.set_margin_bottom(2)
        row.set_child(label)
        row.display_name = output["display_name"]
        app.output_targets_list.append(row)
        app.output_target_rows[(row.player_id, row.local_output_id)] = row

    _populate_group_players_list(app, unique_outputs)

    selected = app.output_manager.get_selected_output()
    if not selected:
        return
    key = (selected["player_id"], selected["local_output_id"])
    row = app.output_target_rows.get(key)
    if not row:
        return
    app.suppress_output_selection = True
    app.output_targets_list.select_row(row)
    app.suppress_output_selection = False


def on_output_selected(app) -> None:
    GLib.idle_add(app._apply_output_selected)


def _apply_output_selected(app) -> None:
    selected = app.output_manager.get_selected_output()
    display_name = selected["display_name"] if selected else "This Computer"
    app.output_selected_name = display_name
    if app.output_menu_button:
        app.output_menu_button.set_tooltip_text(f"Output: {display_name}")
    if app.output_label:
        app.output_label.set_label(display_name)
    app.persist_output_selection()
    if selected and app.output_manager.is_sendspin_player_id(selected["player_id"]):
        app.update_volume_slider(int(round(app.sendspin_manager.volume * 100)))
        local_output_id = app.output_manager.preferred_local_output_id
        if local_output_id != app._last_sendspin_local_output_id:
            app._last_sendspin_local_output_id = local_output_id
            app.on_local_output_selection_changed()
    app.group_members_seed_player_id = None
    app.grouped_player_ids = set()
    _populate_group_players_list(
        app,
        app.output_manager.get_output_targets(),
    )
    if hasattr(app, "refresh_playback_settings"):
        app.refresh_playback_settings()


def on_output_loading_changed(app) -> None:
    GLib.idle_add(app._apply_output_loading_changed)


def _apply_output_loading_changed(app) -> None:
    app.set_output_status(app.output_manager.status_message)


def on_local_output_selection_changed(app) -> None:
    if not app.sendspin_manager.has_support():
        return
    app.cancel_sendspin_pipeline_teardown()
    if app.playback_state == PlaybackState.PLAYING and app.playback_track_info:
        app._resume_after_sendspin_connect = True
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Output changed while playing; will resume after Sendspin reconnect."
            )
    if os.getenv("SENDSPIN_DEBUG"):
        local_output = app.output_manager.get_preferred_local_output()
        logging.getLogger(__name__).info(
            "Selected local output: %s",
            local_output["name"] if local_output else "System Default",
        )
    app.audio_pipeline.destroy_pipeline()
    app.sendspin_manager.stop()
    if app.server_url:
        app.sendspin_manager.start(app.server_url)


def set_output_status(app, message: str) -> None:
    if not app.output_status_label:
        return
    app.output_status_label.set_text(message)
    app.output_status_label.set_visible(bool(message))


def on_group_player_toggled(app, player_id: str, checked: bool) -> None:
    if not app.server_url:
        return
    primary_player_id = (
        app.output_manager.preferred_player_id if app.output_manager else None
    )
    if not primary_player_id or primary_player_id == player_id:
        return
    thread = threading.Thread(
        target=_group_player_toggle_worker,
        args=(app, primary_player_id, player_id, bool(checked)),
        daemon=True,
    )
    thread.start()


def on_sendspin_connected(app) -> None:
    GLib.idle_add(app.output_manager.refresh)
    if getattr(app, "_resume_after_sendspin_connect", False):
        app._resume_after_sendspin_connect = False
        if os.getenv("SENDSPIN_DEBUG"):
            logging.getLogger(__name__).info(
                "Resuming playback after Sendspin reconnect."
            )
        GLib.idle_add(app.send_playback_command, "resume")


def on_sendspin_disconnected(app) -> None:
    return


def cancel_sendspin_pipeline_teardown(app) -> None:
    teardown_id = app.sendspin_pipeline_teardown_id
    if teardown_id is None:
        return
    try:
        GLib.source_remove(teardown_id)
    except Exception:
        pass
    app.sendspin_pipeline_teardown_id = None


def schedule_sendspin_pipeline_teardown(
    app, delay_ms: int = 2000
) -> None:
    app.cancel_sendspin_pipeline_teardown()
    app.sendspin_pipeline_teardown_id = GLib.timeout_add(
        delay_ms,
        app._sendspin_pipeline_teardown,
    )


def _sendspin_pipeline_teardown(app) -> bool:
    app.sendspin_pipeline_teardown_id = None
    app.audio_pipeline.destroy_pipeline()
    _apply_sendspin_stream_end(app)
    return False


def on_sendspin_stream_start(app, format_info: sendspin.PCMFormat) -> None:
    app.cancel_sendspin_pipeline_teardown()
    app.audio_pipeline.reset_stream_timing()
    sink = None
    local_output = app.output_manager.get_preferred_local_output()
    if local_output:
        sink = app.output_manager.create_sink_for_output(local_output["id"])
    if sink is None:
        sink = app.output_manager.create_default_sink()
    app.audio_pipeline.create_pipeline(
        format_info,
        sink,
        app.sendspin_manager.volume,
        app.sendspin_manager.muted,
    )


def on_sendspin_stream_end(app) -> None:
    app.audio_pipeline.flush()
    app.schedule_sendspin_pipeline_teardown()


def _apply_sendspin_stream_end(app) -> bool:
    if getattr(app, "_resume_after_sendspin_connect", False):
        return False
    if getattr(app.sendspin_manager, "stream_active", False):
        return False
    if app.playback_state == PlaybackState.PAUSED:
        return False
    app.stop_playback()
    return False


def on_sendspin_stream_clear(app) -> None:
    app.audio_pipeline.flush()


def on_sendspin_audio_chunk(
    app, timestamp_us: int, payload: bytes, format_info: sendspin.PCMFormat
) -> None:
    app.cancel_sendspin_pipeline_teardown()
    if getattr(app, "playback_pending", False):
        GLib.idle_add(app.mark_playback_started)
    if not app.audio_pipeline.is_active():
        sink = None
        local_output = app.output_manager.get_preferred_local_output()
        if local_output:
            sink = app.output_manager.create_sink_for_output(local_output["id"])
        if sink is None:
            sink = app.output_manager.create_default_sink()
        app.audio_pipeline.create_pipeline(
            format_info,
            sink,
            app.sendspin_manager.volume,
            app.sendspin_manager.muted,
        )
    app.audio_pipeline.push_audio(timestamp_us, payload, format_info)


def on_sendspin_volume_change(app, volume: int) -> None:
    app.set_sendspin_volume(volume)
    app.update_volume_slider(volume)


def on_sendspin_mute_change(app, muted: bool) -> None:
    app.set_sendspin_muted(muted)
    app.update_mute_button_icon()


def update_volume_slider(app, volume: int) -> None:
    if not app.volume_slider:
        return
    if app.volume_dragging or app.pending_volume_value is not None:
        return
    volume = max(0, min(100, int(volume)))
    current_value = int(round(app.volume_slider.get_value()))
    if current_value == volume:
        app.last_volume_value = volume
        return
    if app.volume_update_id is not None:
        GLib.source_remove(app.volume_update_id)
        app.volume_update_id = None
    app.suppress_volume_changes = True
    try:
        app.volume_slider.set_value(volume)
    finally:
        app.suppress_volume_changes = False
    app.last_volume_value = volume
    app.update_mute_button_icon()


def update_mute_button_icon(app) -> None:
    image = getattr(app, "mute_button_image", None)
    if image is None:
        return
    muted = bool(getattr(app.sendspin_manager, "muted", False))
    if muted:
        icon_name = "audio-volume-muted-symbolic"
    else:
        slider = getattr(app, "volume_slider", None)
        if slider is not None:
            volume = int(round(slider.get_value()))
        else:
            volume = int(round(getattr(app.sendspin_manager, "volume", 0.0) * 100))
        if volume > 66:
            icon_name = "audio-volume-high-symbolic"
        elif volume > 33:
            icon_name = "audio-volume-medium-symbolic"
        else:
            icon_name = "audio-volume-low-symbolic"
    image.set_from_icon_name(icon_name)


def set_sendspin_volume(app, volume: int) -> None:
    volume = max(0, min(100, volume))
    app.sendspin_manager.set_volume_percent(volume)
    app.audio_pipeline.set_volume(app.sendspin_manager.volume)
    if app.mpris_manager:
        app.mpris_manager.notify_volume_changed(app.sendspin_manager.volume)


def set_sendspin_muted(app, muted: bool) -> None:
    app.sendspin_manager.set_muted(muted)
    app.audio_pipeline.set_muted(app.sendspin_manager.muted)


def _maybe_transfer_output(
    app,
    source_player_id: str | None,
    target_player_id: str | None,
) -> None:
    if not source_player_id or not target_player_id:
        return
    if source_player_id == target_player_id:
        return
    if not app.server_url or not app.playback_remote_active:
        return
    if app.playback_state not in (PlaybackState.PLAYING, PlaybackState.PAUSED):
        return
    auto_play = app.playback_state == PlaybackState.PLAYING
    thread = threading.Thread(
        target=_transfer_output_worker,
        args=(app, source_player_id, target_player_id, auto_play),
        daemon=True,
    )
    thread.start()


def _transfer_output_worker(
    app,
    source_player_id: str,
    target_player_id: str,
    auto_play: bool | None,
) -> None:
    error = ""
    try:
        playback.transfer_queue(
            app.client_session,
            app.server_url,
            app.auth_token,
            source_player_id,
            target_player_id,
            auto_play,
        )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "Output transfer failed: %s",
            error,
        )


def _schedule_group_members_refresh(
    app,
    selected_player_id: str | None,
) -> None:
    if not app.server_url or not selected_player_id:
        app.group_members_seed_player_id = None
        app.grouped_player_ids = set()
        return
    if getattr(app, "group_members_seed_player_id", None) == selected_player_id:
        return
    if (
        getattr(app, "group_members_refresh_player_id", None)
        == selected_player_id
    ):
        return
    app.group_members_refresh_player_id = selected_player_id
    thread = threading.Thread(
        target=_group_members_refresh_worker,
        args=(app, selected_player_id),
        daemon=True,
    )
    thread.start()


def _group_members_refresh_worker(
    app,
    selected_player_id: str,
) -> None:
    member_ids: list[str] = []
    error = ""
    try:
        member_ids = playback.fetch_group_member_ids(
            app.client_session,
            app.server_url,
            app.auth_token,
            selected_player_id,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(
        _on_group_members_refreshed,
        app,
        selected_player_id,
        member_ids,
        error,
    )


def _on_group_members_refreshed(
    app,
    selected_player_id: str,
    member_ids: list[str],
    error: str,
) -> bool:
    current_selected = (
        app.output_manager.get_selected_output() if app.output_manager else None
    )
    current_selected_player_id = (
        current_selected.get("player_id") if current_selected else None
    )
    if current_selected_player_id != selected_player_id:
        if (
            getattr(app, "group_members_refresh_player_id", None)
            == selected_player_id
        ):
            app.group_members_refresh_player_id = None
        return False
    if (
        getattr(app, "group_members_refresh_player_id", None)
        == selected_player_id
    ):
        app.group_members_refresh_player_id = None
    if error:
        logging.getLogger(__name__).warning(
            "Unable to fetch grouped players: %s",
            error,
        )
        app.group_members_seed_player_id = selected_player_id
        return False
    app.grouped_player_ids = {
        str(member_id)
        for member_id in member_ids
        if member_id
    }
    app.group_members_seed_player_id = selected_player_id
    _populate_group_players_list(
        app,
        app.output_manager.get_output_targets() if app.output_manager else [],
    )
    return False


def _populate_group_players_list(app, outputs: list[dict]) -> None:
    group_box = getattr(app, "output_group_players_box", None)
    if group_box is None:
        return
    ui_utils.clear_container(group_box)
    selected = app.output_manager.get_selected_output() if app.output_manager else None
    selected_player_id = selected.get("player_id") if selected else None
    _schedule_group_members_refresh(app, selected_player_id)
    grouped_ids = set(getattr(app, "grouped_player_ids", set()) or set())
    by_player_id: dict[str, str] = {}
    for output in outputs or []:
        player_id = output.get("player_id")
        display_name = output.get("display_name") or player_id
        if not player_id or player_id in by_player_id:
            continue
        by_player_id[player_id] = display_name
    app.output_group_rows = {}
    app.output_group_populating = True
    try:
        for player_id, display_name in by_player_id.items():
            check = Gtk.CheckButton(label=display_name)
            check.set_halign(Gtk.Align.START)
            if selected_player_id and player_id == selected_player_id:
                check.set_active(True)
                check.set_sensitive(False)
            else:
                check.set_active(player_id in grouped_ids)
                check.connect(
                    "toggled",
                    lambda button, pid=player_id: app.on_group_player_toggled(
                        pid,
                        button.get_active(),
                    ),
                )
            group_box.append(check)
            app.output_group_rows[player_id] = check
    finally:
        app.output_group_populating = False


def _group_player_toggle_worker(
    app,
    primary_player_id: str,
    player_id: str,
    checked: bool,
) -> None:
    grouped_ids: set[str] = set()
    error = ""
    try:
        grouped_ids = {
            str(member_id)
            for member_id in playback.fetch_group_member_ids(
                app.client_session,
                app.server_url,
                app.auth_token,
                primary_player_id,
            )
            if member_id and str(member_id) != primary_player_id
        }
        if checked:
            grouped_ids.add(player_id)
            playback.group_players(
                app.client_session,
                app.server_url,
                app.auth_token,
                primary_player_id,
                sorted(grouped_ids),
            )
        else:
            was_grouped = player_id in grouped_ids
            grouped_ids.discard(player_id)
            if was_grouped:
                playback.ungroup_player(
                    app.client_session,
                    app.server_url,
                    app.auth_token,
                    player_id,
                )
            if grouped_ids:
                playback.group_players(
                    app.client_session,
                    app.server_url,
                    app.auth_token,
                    primary_player_id,
                    sorted(grouped_ids),
                )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "Group players update failed: %s",
            error,
        )
    else:
        app.grouped_player_ids = grouped_ids
        app.group_members_seed_player_id = primary_player_id
    GLib.idle_add(
        _populate_group_players_list,
        app,
        app.output_manager.get_output_targets() if app.output_manager else [],
    )


def set_output_volume(app, volume: int) -> None:
    volume = max(0, min(100, volume))
    app.last_volume_value = volume
    if app.output_manager.is_sendspin_player_id(app.output_manager.preferred_player_id):
        app.set_sendspin_volume(volume)
    else:
        if app.mpris_manager:
            app.mpris_manager.notify_volume_changed(volume / 100.0)
    app.update_volume_slider(volume)
    if (
        not app.server_url
        or not app.output_manager.preferred_player_id
        or app.output_manager.is_sendspin_player_id(
            app.output_manager.preferred_player_id
        )
    ):
        return
    thread = threading.Thread(
        target=app._volume_command_worker,
        args=(app.output_manager.preferred_player_id, volume),
        daemon=True,
    )
    thread.start()


def _volume_command_worker(
    app,
    player_id: str,
    volume: int,
) -> None:
    error = ""
    try:
        playback.set_player_volume(
            app.client_session,
            app.server_url,
            app.auth_token,
            player_id,
            volume,
        )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning("Volume update failed: %s", error)
