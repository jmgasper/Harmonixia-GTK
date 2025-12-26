#!/usr/bin/env python3
import concurrent.futures
import logging
import os
import sys
import threading

import gi

import app_helpers
from constants import APP_ID
from music_assistant import (
    audio_pipeline,
    client_session,
    library_manager,
    output_handlers,
    output_manager,
    playback_state,
    sendspin,
    settings_manager,
)
from music_assistant.mpris import MPRISManager
from music_assistant_models.enums import PlaybackState
from ui import (
    album_detail,
    album_grid,
    album_operations,
    artist_detail,
    artist_operations,
    event_handlers,
    home_manager,
    home_section,
    playlist_detail,
    playlist_operations,
    playback_controls,
    search_manager,
    search_section,
    settings_panel,
    sidebar,
    ui_utils,
)

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

log_level = logging.DEBUG if os.getenv("MA_DEBUG") else logging.INFO
log_format = "%(levelname)s %(name)s: %(message)s"
logging.basicConfig(
    level=log_level,
    format=log_format,
)
if log_level == logging.DEBUG and not os.getenv("MA_DEBUG_RESPONSES"):
    logging.getLogger("music_assistant_client.connection").setLevel(
        logging.INFO
    )
if os.getenv("SENDSPIN_DEBUG") and log_level != logging.DEBUG:
    sendspin_handler = logging.StreamHandler()
    sendspin_handler.setLevel(logging.DEBUG)
    sendspin_handler.setFormatter(logging.Formatter(log_format))
    sendspin_handler._sendspin_debug = True
    for logger_name in (
        "aiosendspin",
        "music_assistant.sendspin",
        "music_assistant.audio_pipeline",
    ):
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        if not any(
            getattr(handler, "_sendspin_debug", False)
            for handler in logger.handlers
        ):
            logger.addHandler(sendspin_handler)
    logging.getLogger("music_assistant.sendspin").info(
        "SENDSPIN_DEBUG enabled.",
    )


class MusicApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self.server_url = ""
        self.auth_token = ""
        self.log_albums = False
        self.log_artists = False
        self.log_albums_path = "ma_albums.json"
        self.log_artists_path = "ma_artists.json"
        self.configure_library_logging()
        for name in (
            "window", "mpris_manager", "main_stack", "albums_flow",
            "albums_scroller", "artists_list", "artist_albums_view", "artist_albums_title",
            "artist_albums_header", "artist_albums_status_label", "artist_albums_flow",
            "artist_albums_previous_view", "albums_header", "album_type_filter_button",
            "artists_header", "library_status_label", "library_loading_overlay", "library_loading_spinner",
            "library_loading_label", "settings_button", "sidebar_now_playing_art", "sidebar_now_playing_art_url",
            "settings_server_entry", "settings_token_entry", "settings_status_label", "settings_connect_button",
            "settings_previous_view", "settings_output_backend_combo", "settings_pulse_device_entry", "settings_alsa_device_entry",
            "eq_settings_card", "eq_preset_search_entry", "eq_graph_area", "eq_graph_placeholder", "settings_scrolled_window",
            "gtk_debug_status_label", "library_list", "home_nav_list", "playlists_list",
            "playlists_status_label", "playlists_add_button", "home_recently_played_list", "home_recently_added_list",
            "home_recently_played_status", "home_recently_added_status", "home_recently_played_refresh_id", "album_detail_view",
            "album_detail_background", "album_detail_art", "album_detail_title", "album_detail_artist",
            "album_detail_status_label", "album_detail_play_button", "album_tracks_store", "album_tracks_sort_model",
            "album_tracks_selection", "album_tracks_view", "playlist_detail_view", "playlist_detail_background",
            "playlist_detail_art", "playlist_detail_title", "playlist_detail_status_label", "playlist_tracks_store",
            "playlist_tracks_sort_model",
            "playlist_tracks_selection", "playlist_tracks_view", "current_artist", "current_album", "current_playlist", "playback_album",
            "playback_track_info", "playback_track_identity", "playback_track_index", "playback_queue_identity", "playback_last_tick",
            "playback_timer_id", "playback_progress_bar", "playback_time_current_label", "playback_time_total_label",
            "now_playing_title_button", "now_playing_title_label", "now_playing_artist_button", "now_playing_artist_label",
            "play_pause_button", "play_pause_image", "playback_sync_id",
            "previous_button", "next_button", "volume_slider", "eq_button", "volume_update_id",
            "pending_volume_value", "output_menu_button", "output_popover", "output_targets_list", "sendspin_pipeline_teardown_id",
            "output_status_label", "output_label", "_last_sendspin_local_output_id", "output_manager",
            "search_entry", "search_results_view", "search_status_label", "search_playlists_section",
            "search_playlists_flow", "search_albums_section", "search_albums_flow", "search_artists_section",
            "search_artists_list", "search_tracks_section", "search_tracks_store", "search_tracks_sort_model",
            "search_tracks_selection", "search_tracks_view", "search_tracks_scroller", "search_previous_view",
            "search_previous_album", "search_previous_album_tracks", "search_context_album", "search_debounce_id",
            "search_request_id", "client_session",
        ):
            setattr(self, name, None)
        for name in (
            "library_loading", "playlists_loading", "playlists_refresh_pending", "home_recently_played_loading",
            "home_recently_added_loading", "track_bind_logged", "playback_remote_active", "auto_load_attempted",
            "volume_dragging", "suppress_volume_changes", "suppress_track_selection", "suppress_output_selection", "playback_sync_inflight",
            "_resume_after_sendspin_connect", "search_loading", "search_active",
        ):
            setattr(self, name, False)
        self.eq_enabled = False
        self.eq_selected_preset = None
        self.eq_preset_combo = None
        self.eq_preset_search_entry = None
        self.eq_toggle_switch = None
        self.eq_details_view = None
        self.search_query = ""
        self.search_request_id = 0
        self.search_track_rows = []
        self.albums_scroll_position = 0.0
        self.album_type_check_buttons = {}
        self.selected_album_types = set()
        self.library_albums = []
        self.playlists = []
        self.image_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=6,
            thread_name_prefix="album-art",
        )
        self.album_detail_previous_view = "albums"
        self.artist_albums_previous_view = "artists"
        self.current_album_tracks = []
        self.playback_album_tracks = []
        self.playback_state = PlaybackState.IDLE
        self.playback_elapsed = 0.0
        self.playback_duration = 0
        self.output_target_rows = {}
        self.output_selected_name = "This Computer"
        self.output_backend = ""
        self.output_pulse_device = ""
        self.output_alsa_device = ""
        self.local_device_names = ui_utils.get_local_device_names()
        self.audio_pipeline = audio_pipeline.AudioPipeline(
            get_supported_formats=lambda: (
                self.output_manager.get_preferred_local_output_formats()
                if self.output_manager
                else []
            )
        )
        self.sendspin_manager = sendspin.SendspinManager(
            get_supported_formats=lambda: (
                self.output_manager.get_preferred_local_output_formats_for_sendspin()
                if self.output_manager
                else []
            ),
            on_connected=self.on_sendspin_connected,
            on_disconnected=self.on_sendspin_disconnected,
            on_stream_start=self.on_sendspin_stream_start,
            on_stream_end=self.on_sendspin_stream_end,
            on_stream_clear=self.on_sendspin_stream_clear,
            on_audio_chunk=self.on_sendspin_audio_chunk,
            on_volume_change=self.on_sendspin_volume_change,
            on_mute_change=self.on_sendspin_mute_change,
        )
        self.client_session = client_session.ClientSession()
        self.output_manager = output_manager.OutputManager(
            get_server_url=lambda: self.server_url,
            get_auth_token=lambda: self.auth_token,
            client_session=self.client_session,
            get_sendspin_client_id=lambda: self.sendspin_manager.client_id,
            get_sendspin_client_name=lambda: self.sendspin_manager.client_name,
            has_sendspin_support=lambda: self.sendspin_manager.has_support(),
            get_output_backend=lambda: self.output_backend,
            get_pulse_device=lambda: self.output_pulse_device,
            get_alsa_device=lambda: self.output_alsa_device,
            local_device_names=self.local_device_names,
            on_outputs_changed=self.on_outputs_changed,
            on_output_selected=self.on_output_selected,
            on_loading_state_changed=self.on_output_loading_changed,
        )
        self.load_settings()
        self._apply_startup_eq_preset()
        self.client_session.set_server(self.server_url, self.auth_token)
        self.sendspin_manager.ensure_client_id()

    def _apply_startup_eq_preset(self) -> None:
        if not self.eq_selected_preset:
            return
        self._load_eq_preset_in_background(self.eq_selected_preset)

    def _apply_eq_preset(self, preset: dict, preset_id: str) -> None:
        try:
            from music_assistant import eq_presets

            eq_presets.apply_preset_to_pipeline(
                preset,
                self.audio_pipeline,
            )
            self.audio_pipeline.set_eq_enabled(self.eq_enabled)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to apply EQ preset %s: %s",
                preset_id,
                exc,
            )

    def _load_eq_preset_in_background(self, preset_id: str) -> None:
        thread = threading.Thread(
            target=self._load_eq_preset_worker,
            args=(preset_id,),
            daemon=True,
        )
        thread.start()

    def _load_eq_preset_worker(self, preset_id: str) -> None:
        try:
            from music_assistant import eq_presets

            presets = eq_presets.load_presets()
            preset = eq_presets.get_preset_by_name(preset_id, presets)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to load EQ presets for %s: %s",
                preset_id,
                exc,
            )
            return
        if not preset:
            logging.getLogger(__name__).warning(
                "EQ preset %s not found after loading presets.",
                preset_id,
            )
            return
        GLib.idle_add(
            self._apply_eq_preset_from_worker,
            preset_id,
            preset,
        )

    def _apply_eq_preset_from_worker(
        self,
        preset_id: str,
        preset: dict,
    ) -> bool:
        if self.eq_selected_preset != preset_id:
            return False
        self._apply_eq_preset(preset, preset_id)
        return False

    def do_activate(self) -> None:
        if not self.window:
            self.window = Gtk.ApplicationWindow(application=self)
            self.window.set_title("Music Assistant")
            self.window.set_default_size(1180, 720)
            self.window.set_child(self.build_ui())
            callbacks = {
                "on_play_pause": lambda: self.on_play_pause_clicked(
                    self.play_pause_button
                ),
                "on_next": lambda: self.on_next_clicked(self.next_button),
                "on_previous": lambda: self.on_previous_clicked(
                    self.previous_button
                ),
                "on_raise": lambda: self.window.present() if self.window else None,
                "on_quit": self.quit,
                "on_set_volume": self.set_output_volume,
                "on_update_volume_slider": self.update_volume_slider,
            }
            state_getters = {
                "get_playback_state": lambda: self.playback_state,
                "get_track_info": lambda: self.playback_track_info,
                "get_track_index": lambda: self.playback_track_index,
                "get_album_tracks": lambda: self.playback_album_tracks,
                "get_elapsed": lambda: self.playback_elapsed,
                "get_window": lambda: self.window,
            }
            self.mpris_manager = MPRISManager(callbacks, state_getters)
            self.mpris_manager.notify_volume_changed(self.sendspin_manager.volume)
            self.mpris_manager.start()
            self.mpris_manager.setup_media_keys(self.window)
            self.log_gtk_environment()
            ui_utils.load_custom_fonts(self.get_font_paths())
            ui_utils.apply_css(self.get_css_path())
            self.update_settings_entries()
            self.output_manager.start_monitoring()
            self.output_manager.refresh()
            self.sendspin_manager.start(self.server_url)
        if not self.auto_load_attempted:
            self.auto_load_attempted = True
            if self.server_url:
                GLib.idle_add(self.load_library)
        self.window.present()

    def do_shutdown(self) -> None:
        if self.image_executor:
            self.image_executor.shutdown(wait=False)
        self.sendspin_manager.stop()
        self.audio_pipeline.destroy_pipeline()
        self.output_manager.stop_monitoring()
        if self.client_session:
            self.client_session.stop()
        if self.mpris_manager:
            self.mpris_manager.stop()
        super().do_shutdown()

    def refresh_output_targets(self) -> None:
        if self.output_manager:
            self.output_manager.refresh()

    def build_ui(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.append(playback_controls.build_controls(self))
        root.append(self.build_content())
        return root

    def build_content(self) -> Gtk.Widget:
        content = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        content.set_resize_start_child(False)
        content.set_shrink_start_child(False)
        content.set_wide_handle(False)

        content.set_start_child(sidebar.build_sidebar(self))
        content.set_end_child(self.build_main_area())
        return content

    def build_main_area(self) -> Gtk.Widget:
        stack = Gtk.Stack()
        stack.set_hexpand(True)
        stack.set_vexpand(True)

        stack.add_named(home_section.build_home_section(self), "home")
        stack.add_named(search_section.build_search_section(self), "search")
        stack.add_named(album_grid.build_album_section(self), "albums")
        stack.add_named(album_detail.build_album_detail_section(self), "album-detail")
        stack.add_named(
            playlist_detail.build_playlist_detail_section(self),
            "playlist-detail",
        )
        stack.add_named(self.build_artists_section(), "artists")
        stack.add_named(
            artist_detail.build_artist_albums_section(self),
            "artist-albums",
        )
        stack.add_named(settings_panel.build_settings_section(self), "settings")
        stack.set_visible_child_name("home")
        self.main_stack = stack
        return stack


def _bind_methods(source, names) -> None:
    for name in names:
        setattr(MusicApp, name, getattr(source, name))


def _bind_static_methods(source, names) -> None:
    for name in names:
        setattr(MusicApp, name, staticmethod(getattr(source, name)))


for binder, source, names in (
    (_bind_methods, app_helpers, ("configure_library_logging", "get_settings_path", "get_css_path", "get_cache_dir", "get_font_paths", "log_gtk_environment", "get_album_type_value")),
    (_bind_static_methods, app_helpers, ("write_json_log", "build_sample_albums", "normalize_album_type", "pick_album_value")),
    (_bind_static_methods, album_grid, ("pick_icon_name",)),
    (_bind_methods, settings_manager, ("load_settings", "save_settings", "persist_sendspin_settings", "persist_output_selection", "persist_eq_settings", "update_settings_entries", "connect_to_server")),
    (_bind_methods, settings_panel, ("navigate_to_eq_settings",)),
    (_bind_methods, event_handlers, ("on_track_action_clicked", "on_track_selection_changed", "clear_track_selection", "on_play_pause_clicked", "on_previous_clicked", "on_next_clicked", "on_volume_changed", "_apply_volume_change", "on_volume_drag_begin", "on_volume_drag_end", "on_now_playing_title_clicked", "on_now_playing_artist_clicked", "on_now_playing_art_clicked")),
    (_bind_methods, output_handlers, ("on_output_popover_mapped", "on_output_target_activated", "on_outputs_changed", "_apply_outputs_changed", "on_output_selected", "_apply_output_selected", "on_output_loading_changed", "_apply_output_loading_changed", "on_local_output_selection_changed", "set_output_status", "on_sendspin_connected", "on_sendspin_disconnected", "on_sendspin_stream_start", "on_sendspin_stream_end", "on_sendspin_stream_clear", "on_sendspin_audio_chunk", "on_sendspin_volume_change", "on_sendspin_mute_change", "update_volume_slider", "set_sendspin_volume", "set_sendspin_muted", "set_output_volume", "_volume_command_worker", "cancel_sendspin_pipeline_teardown", "schedule_sendspin_pipeline_teardown", "_sendspin_pipeline_teardown")),
    (_bind_methods, album_operations, ("show_album_detail", "set_album_detail_status", "get_albums_scroll_position", "restore_album_scroll", "load_album_tracks", "_load_album_tracks_worker", "_fetch_album_tracks_async", "on_album_tracks_loaded", "populate_track_table", "on_album_detail_close", "on_album_play_clicked", "is_same_album")),
    (_bind_static_methods, album_operations, ("get_album_name", "get_album_track_candidates", "get_album_identity")),
    (_bind_methods, artist_operations, ("show_artist_albums", "refresh_artist_albums", "populate_artist_album_flow", "on_artist_row_activated", "on_artist_album_activated", "on_artist_albums_back")),
    (_bind_methods, playlist_operations, ("show_playlist_detail", "set_playlist_detail_status", "load_playlist_tracks", "_load_playlist_tracks_worker", "_fetch_playlist_tracks_async", "on_playlist_tracks_loaded", "populate_playlist_track_table")),
    (_bind_methods, playback_state, ("start_playback_from_track", "start_playback_from_index", "handle_previous_action", "handle_next_action", "restart_current_track", "sync_playback_highlight", "stop_playback", "set_playback_state", "update_play_pause_icon", "ensure_playback_timer", "on_playback_tick", "update_now_playing", "update_sidebar_now_playing_art", "update_playback_progress_ui", "ensure_remote_playback_sync", "stop_remote_playback_sync", "_remote_playback_sync_tick", "_sync_remote_playback_worker", "_fetch_remote_playback_state_async", "_apply_remote_playback_state", "queue_album_playback", "_play_album_worker", "send_playback_command", "_playback_command_worker", "send_playback_index", "_playback_index_worker")),
    (_bind_methods, library_manager, ("load_library", "_load_library_worker", "on_library_loaded", "set_loading_state", "set_loading_message", "set_status", "populate_artists_list", "build_artists_section")),
    (_bind_methods, search_manager, ("on_search_changed", "on_search_activated", "activate_search_view", "restore_search_view", "clear_search", "schedule_search", "_run_search", "_start_search", "_search_worker", "_fetch_search_results_async", "on_search_results_loaded", "set_search_status", "clear_search_results", "populate_search_playlists", "populate_search_albums", "populate_search_artists", "populate_search_tracks", "on_search_album_activated", "on_search_playlist_activated")),
    (_bind_methods, home_manager, ("refresh_home_sections", "clear_home_recent_lists", "schedule_home_recently_played_refresh", "_handle_home_recently_played_refresh", "refresh_home_recently_played", "refresh_home_recently_added", "_load_recently_played_worker", "_load_recently_added_worker", "_fetch_recently_played_albums_async", "_fetch_recently_added_albums_async", "on_recently_played_loaded", "on_recently_added_loaded", "clear_home_album_selection")),
):
    binder(source, names)


def main() -> int:
    app = MusicApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
