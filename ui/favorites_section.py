from gi.repository import Gtk, Pango

from ui import favorites_manager, track_table


def build_favorites_section(app) -> Gtk.Widget:
    overlay = Gtk.Overlay()
    overlay.add_css_class("playlist-detail")
    overlay.set_hexpand(True)
    overlay.set_vexpand(True)

    background = Gtk.Picture()
    background.add_css_class("playlist-detail-bg")
    background.set_hexpand(True)
    background.set_vexpand(True)
    background.set_halign(Gtk.Align.FILL)
    background.set_valign(Gtk.Align.FILL)
    background.set_can_shrink(True)
    if hasattr(background, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        background.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(background, "set_keep_aspect_ratio"):
        background.set_keep_aspect_ratio(True)
    overlay.set_child(background)

    dimmer = Gtk.Box()
    dimmer.add_css_class("playlist-detail-dim")
    dimmer.set_hexpand(True)
    dimmer.set_vexpand(True)
    dimmer.set_halign(Gtk.Align.FILL)
    dimmer.set_valign(Gtk.Align.FILL)
    overlay.add_overlay(dimmer)

    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    container.add_css_class("playlist-detail-content")
    container.set_hexpand(True)
    container.set_vexpand(True)
    container.set_halign(Gtk.Align.FILL)
    container.set_valign(Gtk.Align.FILL)

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    title = Gtk.Label(label="Favorites", xalign=0)
    title.add_css_class("playlist-detail-title")
    title.set_wrap(True)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    subtitle = Gtk.Label(label="All favorited tracks", xalign=0)
    subtitle.add_css_class("detail-artist")
    subtitle.set_wrap(True)
    subtitle.set_ellipsize(Pango.EllipsizeMode.END)
    header.append(title)
    header.append(subtitle)

    controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    controls_row.set_halign(Gtk.Align.START)

    play_button = Gtk.Button()
    play_button.add_css_class("suggested-action")
    play_button.add_css_class("detail-play")
    play_button.set_halign(Gtk.Align.START)
    play_button.set_tooltip_text("Play all")
    play_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
    play_icon.set_pixel_size(18)
    play_button.set_child(play_icon)
    play_button.set_sensitive(False)
    play_button.set_visible(False)
    play_button.connect(
        "clicked",
        lambda _btn: favorites_manager.on_favorites_play_clicked(app),
    )
    controls_row.append(play_button)

    shuffle_icon_name = app.pick_icon_name(
        ["media-playlist-shuffle-symbolic", "media-playlist-shuffle"]
    )
    shuffle_button = Gtk.Button()
    shuffle_button.add_css_class("detail-play")
    shuffle_button.set_halign(Gtk.Align.START)
    shuffle_button.set_tooltip_text("Shuffle play")
    shuffle_icon = Gtk.Image.new_from_icon_name(shuffle_icon_name)
    shuffle_icon.set_pixel_size(18)
    shuffle_button.set_child(shuffle_icon)
    shuffle_button.set_sensitive(False)
    shuffle_button.set_visible(False)
    shuffle_button.connect(
        "clicked",
        lambda _btn: favorites_manager.on_favorites_shuffle_clicked(app),
    )
    controls_row.append(shuffle_button)
    header.append(controls_row)
    container.append(header)

    tracks_label = Gtk.Label(label="Tracks")
    tracks_label.add_css_class("section-title")
    tracks_label.set_xalign(0)
    container.append(tracks_label)

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    container.append(status)

    filter_entry = Gtk.Entry()
    filter_entry.set_placeholder_text("Filter by title or artist…")
    filter_entry.add_css_class("favorites-filter-entry")
    filter_entry.set_hexpand(True)
    filter_entry.connect(
        "changed",
        lambda entry, *_: favorites_manager.on_favorites_filter_changed(app, entry),
    )
    container.append(filter_entry)

    tracks_table = track_table.build_tracks_table(
        app,
        store_attr="favorites_tracks_store",
        sort_model_attr="favorites_tracks_sort_model",
        selection_attr="favorites_tracks_selection",
        view_attr="favorites_tracks_view",
        disc_column_attr="favorites_tracks_disc_column",
        use_track_art=True,
    )
    tracks_scroller = Gtk.ScrolledWindow()
    tracks_scroller.set_policy(
        Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
    )
    tracks_scroller.set_child(tracks_table)
    if hasattr(tracks_scroller, "set_propagate_natural_height"):
        tracks_scroller.set_propagate_natural_height(True)
    tracks_scroller.set_vexpand(False)
    container.append(tracks_scroller)

    overlay.add_overlay(container)

    app.favorites_status_label = status
    app.favorites_play_button = play_button
    app.favorites_shuffle_button = shuffle_button
    app.favorites_filter_entry = filter_entry
    return overlay
