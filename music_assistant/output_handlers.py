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


def set_sendspin_volume(app, volume: int) -> None:
    volume = max(0, min(100, volume))
    app.sendspin_manager.set_volume_percent(volume)
    app.audio_pipeline.set_volume(app.sendspin_manager.volume)
    if app.mpris_manager:
        app.mpris_manager.notify_volume_changed(app.sendspin_manager.volume)


def set_sendspin_muted(app, muted: bool) -> None:
    app.sendspin_manager.set_muted(muted)
    app.audio_pipeline.set_muted(app.sendspin_manager.muted)


def _volume_step_size(volume: int) -> int:
    if volume < 5 or volume > 95:
        return 1
    if volume < 20 or volume > 80:
        return 2
    return 5


def _calculate_volume_steps(
    current_volume: int,
    target_volume: int,
) -> tuple[int, int, int]:
    if current_volume == target_volume:
        return 0, 0, current_volume
    direction = 1 if target_volume > current_volume else -1
    steps = 0
    volume = current_volume
    # Mirror Music Assistant's cmd_volume_up/down step sizes.
    while volume != target_volume:
        step = _volume_step_size(volume)
        if step <= 0:
            break
        next_volume = volume + (step * direction)
        if direction > 0:
            volume = min(100, next_volume)
            steps += 1
            if volume >= target_volume:
                break
        else:
            volume = max(0, next_volume)
            steps += 1
            if volume <= target_volume:
                break
        if volume in (0, 100):
            break
    return direction, steps, volume


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


def set_output_volume(app, volume: int) -> None:
    volume = max(0, min(100, volume))
    current_volume = app.last_volume_value
    if current_volume is None:
        if app.volume_slider:
            current_volume = int(round(app.volume_slider.get_value()))
        else:
            current_volume = volume
    direction, steps, expected_volume = _calculate_volume_steps(
        current_volume,
        volume,
    )
    app.last_volume_value = expected_volume
    if app.output_manager.is_sendspin_player_id(app.output_manager.preferred_player_id):
        app.set_sendspin_volume(expected_volume)
    else:
        if app.mpris_manager:
            app.mpris_manager.notify_volume_changed(expected_volume / 100.0)
    app.update_volume_slider(expected_volume)
    if (
        not app.server_url
        or not app.output_manager.preferred_player_id
        or steps <= 0
        or direction == 0
    ):
        return
    thread = threading.Thread(
        target=app._volume_command_worker,
        args=(app.output_manager.preferred_player_id, direction, steps),
        daemon=True,
    )
    thread.start()


def _volume_command_worker(
    app,
    player_id: str,
    direction: int,
    steps: int,
) -> None:
    if direction == 0 or steps <= 0:
        return
    error = ""
    try:
        playback.step_player_volume(
            app.client_session,
            app.server_url,
            app.auth_token,
            player_id,
            direction,
            steps,
        )
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning("Volume update failed: %s", error)
