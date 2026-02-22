"""Sleep timer helpers."""

from gi.repository import GLib


def start_sleep_timer(app, minutes: int) -> None:
    cancel_sleep_timer(app)
    duration_minutes = max(1, int(minutes))
    app.sleep_timer_remaining_seconds = duration_minutes * 60
    app.sleep_timer_id = GLib.timeout_add(60_000, app._sleep_timer_tick)
    _update_sleep_timer_tooltip(app)


def cancel_sleep_timer(app) -> None:
    timer_id = getattr(app, "sleep_timer_id", None)
    if timer_id:
        try:
            GLib.source_remove(timer_id)
        except Exception:
            pass
    app.sleep_timer_id = None
    app.sleep_timer_remaining_seconds = 0
    _update_sleep_timer_tooltip(app)


def _sleep_timer_tick(app) -> bool:
    remaining = int(getattr(app, "sleep_timer_remaining_seconds", 0))
    remaining -= 60
    app.sleep_timer_remaining_seconds = max(0, remaining)
    if app.sleep_timer_remaining_seconds <= 0:
        cancel_sleep_timer(app)
        app.send_playback_command("stop")
        return False
    _update_sleep_timer_tooltip(app)
    return True


def _update_sleep_timer_tooltip(app) -> None:
    button = getattr(app, "sleep_timer_button", None)
    if not button:
        return
    remaining = int(getattr(app, "sleep_timer_remaining_seconds", 0))
    if remaining > 0:
        minutes = max(1, remaining // 60)
        button.set_tooltip_text(f"Sleep: {minutes} min")
    else:
        button.set_tooltip_text("Sleep Timer")
