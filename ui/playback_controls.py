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

    art_thumb = Gtk.Picture()
    art_thumb.add_css_class("now-playing-art-thumb")
    art_thumb.set_size_request(48, 48)
    art_thumb.set_halign(Gtk.Align.START)
    art_thumb.set_valign(Gtk.Align.CENTER)
    art_thumb.set_can_shrink(True)
    art_thumb.set_visible(False)
    if hasattr(art_thumb, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        art_thumb.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(art_thumb, "set_keep_aspect_ratio"):
        art_thumb.set_keep_aspect_ratio(False)

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

    provider_icon = Gtk.Image()
    provider_icon.add_css_class("now-playing-provider-icon")
    provider_icon.set_pixel_size(14)
    provider_icon.set_visible(False)

    provider_label = Gtk.Label(label="")
    provider_label.add_css_class("now-playing-provider-label")
    provider_label.set_xalign(0)
    provider_label.set_ellipsize(Pango.EllipsizeMode.END)
    provider_label.set_single_line_mode(True)

    provider_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    provider_box.add_css_class("now-playing-provider")
    provider_box.set_halign(Gtk.Align.END)
    provider_box.set_valign(Gtk.Align.CENTER)
    provider_box.set_visible(False)
    provider_box.append(provider_icon)
    provider_box.append(provider_label)

    title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    title_row.set_hexpand(True)
    title_row.set_valign(Gtk.Align.CENTER)
    title_row.append(title_button)
    title_row.append(provider_box)

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

    quality = Gtk.Label(label="")
    quality.add_css_class("now-playing-quality")
    quality.set_xalign(1)
    quality.set_halign(Gtk.Align.END)
    quality.set_ellipsize(Pango.EllipsizeMode.END)
    quality.set_single_line_mode(True)
    quality.set_visible(False)

    artist_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    artist_row.set_hexpand(True)
    artist_row.set_valign(Gtk.Align.CENTER)
    artist_row.append(artist_button)
    artist_row.append(quality)

    progress_row = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=8,
    )
    progress_row.set_hexpand(True)
    progress_row.set_valign(Gtk.Align.CENTER)

    time_current = Gtk.Label(label="0:00")
    time_current.add_css_class("now-playing-time")
    time_current.set_xalign(0)

    seek_scale = Gtk.Scale.new_with_range(
        Gtk.Orientation.HORIZONTAL,
        0.0,
        1.0,
        0.001,
    )
    seek_scale.add_css_class("seek-scale")
    seek_scale.set_draw_value(False)
    seek_scale.set_hexpand(True)
    seek_scale.set_valign(Gtk.Align.CENTER)
    seek_scale.set_value(0.0)
    seek_scale.connect("value-changed", app.on_seek_scale_changed)
    seek_gesture = Gtk.GestureClick.new()
    seek_gesture.connect("pressed", app.on_seek_drag_begin)
    seek_gesture.connect("released", app.on_seek_drag_end)
    seek_scale.add_controller(seek_gesture)

    time_total = Gtk.Label(label="0:00")
    time_total.add_css_class("now-playing-time")
    time_total.set_xalign(1)

    progress_row.append(time_current)
    progress_row.append(seek_scale)
    progress_row.append(time_total)

    now_playing.append(title_row)
    now_playing.append(artist_row)
    now_playing.append(progress_row)

    now_playing_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    now_playing_row.set_hexpand(True)
    now_playing_row.set_valign(Gtk.Align.CENTER)
    now_playing_row.append(art_thumb)
    now_playing_row.append(now_playing)

    app.previous_button = previous_button
    app.play_pause_button = play_pause_button
    app.play_pause_image = play_pause_image
    app.next_button = next_button
    app.now_playing_title_button = title_button
    app.now_playing_title_label = title
    app.now_playing_provider_box = provider_box
    app.now_playing_provider_icon = provider_icon
    app.now_playing_provider_label = provider_label
    app.now_playing_artist_button = artist_button
    app.now_playing_artist_label = artist
    app.now_playing_quality_label = quality
    app.now_playing_art_thumb = art_thumb
    app.playback_seek_scale = seek_scale
    app.playback_time_current_label = time_current
    app.playback_time_total_label = time_total

    search_and_volume = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    search_and_volume.set_valign(Gtk.Align.CENTER)

    mute_button_image = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
    mute_button = Gtk.Button()
    mute_button.add_css_class("flat")
    mute_button.add_css_class("mute-button")
    mute_button.set_tooltip_text("Mute / Unmute")
    mute_button.set_child(mute_button_image)
    mute_button.connect("clicked", app.on_mute_button_clicked)
    app.mute_button = mute_button
    app.mute_button_image = mute_button_image

    volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    volume.set_draw_value(False)
    volume.set_valign(Gtk.Align.CENTER)
    volume.set_size_request(120, -1)
    initial_volume = int(round(app.sendspin_manager.volume * 100))
    volume.set_value(initial_volume)
    app.last_volume_value = initial_volume
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

    search_and_volume.append(mute_button)
    search_and_volume.append(volume)
    search_and_volume.append(eq_button)
    app.update_mute_button_icon()

    playback_and_now_playing = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=10,
    )
    playback_and_now_playing.set_hexpand(True)
    playback_and_now_playing.set_valign(Gtk.Align.CENTER)
    playback_and_now_playing.append(playback)
    playback_and_now_playing.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
    playback_and_now_playing.append(now_playing_row)

    controls.append(playback_and_now_playing)
    controls.append(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
    controls.append(search_and_volume)

    return controls
