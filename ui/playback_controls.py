from gi.repository import Gtk, Pango

from ui import output_selector, settings_panel


def build_controls(app) -> Gtk.Widget:
    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    controls.add_css_class("control-bar")

    playback = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    playback.set_valign(Gtk.Align.CENTER)
    previous_button = Gtk.Button()
    previous_button.add_css_class("flat")
    previous_button.set_tooltip_text("Previous")
    previous_button.set_child(
        Gtk.Image.new_from_icon_name("media-skip-backward-symbolic")
    )
    previous_button.connect("clicked", app.on_previous_clicked)
    playback.append(previous_button)

    play_pause_button = Gtk.Button()
    play_pause_button.add_css_class("flat")
    play_pause_button.set_tooltip_text("Play")
    play_pause_image = Gtk.Image.new_from_icon_name(
        "media-playback-start-symbolic"
    )
    play_pause_button.set_child(play_pause_image)
    play_pause_button.connect("clicked", app.on_play_pause_clicked)
    playback.append(play_pause_button)

    next_button = Gtk.Button()
    next_button.add_css_class("flat")
    next_button.set_tooltip_text("Next")
    next_button.set_child(
        Gtk.Image.new_from_icon_name("media-skip-forward-symbolic")
    )
    next_button.connect("clicked", app.on_next_clicked)
    playback.append(next_button)
    playback.append(output_selector.build_output_selector(app))

    now_playing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    now_playing.set_hexpand(True)
    now_playing.set_valign(Gtk.Align.CENTER)
    title = Gtk.Label(label="Not Playing")
    title.add_css_class("now-playing")
    title.set_xalign(0)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    title.set_single_line_mode(True)
    title.set_hexpand(True)

    title_button = Gtk.Button()
    title_button.add_css_class("now-playing-link")
    title_button.set_has_frame(False)
    title_button.set_hexpand(True)
    title_button.set_halign(Gtk.Align.FILL)
    title_button.set_child(title)
    title_button.connect("clicked", app.on_now_playing_title_clicked)

    artist = Gtk.Label(label="")
    artist.add_css_class("now-playing-artist")
    artist.set_xalign(0)
    artist.set_ellipsize(Pango.EllipsizeMode.END)
    artist.set_single_line_mode(True)
    artist.set_hexpand(True)

    artist_button = Gtk.Button()
    artist_button.add_css_class("now-playing-link")
    artist_button.set_has_frame(False)
    artist_button.set_hexpand(True)
    artist_button.set_halign(Gtk.Align.FILL)
    artist_button.set_child(artist)
    artist_button.connect("clicked", app.on_now_playing_artist_clicked)

    progress_row = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=8,
    )
    progress_row.set_hexpand(True)
    progress_row.set_valign(Gtk.Align.CENTER)

    time_current = Gtk.Label(label="0:00")
    time_current.add_css_class("now-playing-time")
    time_current.set_xalign(0)

    progress = Gtk.ProgressBar()
    progress.set_hexpand(True)
    progress.set_valign(Gtk.Align.CENTER)
    progress.set_fraction(0.0)

    time_total = Gtk.Label(label="0:00")
    time_total.add_css_class("now-playing-time")
    time_total.set_xalign(1)

    progress_row.append(time_current)
    progress_row.append(progress)
    progress_row.append(time_total)

    now_playing.append(title_button)
    now_playing.append(artist_button)
    now_playing.append(progress_row)

    app.previous_button = previous_button
    app.play_pause_button = play_pause_button
    app.play_pause_image = play_pause_image
    app.next_button = next_button
    app.now_playing_title_button = title_button
    app.now_playing_title_label = title
    app.now_playing_artist_button = artist_button
    app.now_playing_artist_label = artist
    app.playback_progress_bar = progress
    app.playback_time_current_label = time_current
    app.playback_time_total_label = time_total

    search_and_volume = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    search_and_volume.set_valign(Gtk.Align.CENTER)

    volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    volume.set_draw_value(False)
    volume.set_valign(Gtk.Align.CENTER)
    volume.set_size_request(120, -1)
    initial_volume = int(round(app.sendspin_manager.volume * 100))
    volume.set_value(initial_volume)
    volume.connect("value-changed", app.on_volume_changed)
    drag_gesture = Gtk.GestureClick.new()
    drag_gesture.connect("pressed", app.on_volume_drag_begin)
    drag_gesture.connect("released", app.on_volume_drag_end)
    volume.add_controller(drag_gesture)
    app.volume_slider = volume

    eq_icon_name = app.pick_icon_name(
        [
            "audio-equalizer-symbolic",
            "media-eq-symbolic",
            "multimedia-audio-player-symbolic",
        ]
    )
    eq_button = Gtk.Button()
    eq_button.add_css_class("flat")
    eq_button.add_css_class("eq-button")
    eq_button.set_tooltip_text("Equalizer Settings")
    eq_button.set_child(Gtk.Image.new_from_icon_name(eq_icon_name))
    eq_button.connect(
        "clicked",
        lambda _button: settings_panel.navigate_to_eq_settings(app),
    )
    app.eq_button = eq_button

    search = Gtk.SearchEntry()
    search.set_placeholder_text("Search Library")
    search.set_size_request(200, -1)
    search.connect("search-changed", app.on_search_changed)
    search.connect("activate", app.on_search_activated)
    app.search_entry = search

    search_and_volume.append(Gtk.Label(label="Volume"))
    search_and_volume.append(volume)
    search_and_volume.append(eq_button)
    search_and_volume.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
    search_and_volume.append(search)

    controls.append(playback)
    controls.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
    controls.append(now_playing)
    controls.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
    controls.append(search_and_volume)

    return controls
