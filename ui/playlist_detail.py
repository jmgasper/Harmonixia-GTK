from gi.repository import Gtk, Pango

from constants import DETAIL_ART_SIZE
from ui import playlist_manager, track_table


def build_playlist_detail_section(app) -> Gtk.Widget:
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

    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

    art = Gtk.Picture()
    art.add_css_class("detail-art")
    art.set_size_request(DETAIL_ART_SIZE, DETAIL_ART_SIZE)
    art.set_halign(Gtk.Align.START)
    art.set_valign(Gtk.Align.START)
    art.set_can_shrink(True)
    if hasattr(art, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        art.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(art, "set_keep_aspect_ratio"):
        art.set_keep_aspect_ratio(False)

    title = Gtk.Label(label="Playlist", xalign=0)
    title.add_css_class("playlist-detail-title")
    title.set_wrap(True)
    title.set_ellipsize(Pango.EllipsizeMode.END)

    rename_icon_name = app.pick_icon_name(
        [
            "document-edit-symbolic",
            "edit-symbolic",
            "accessories-text-editor-symbolic",
        ]
    )
    rename_button = Gtk.Button()
    rename_button.add_css_class("playlist-header-button")
    rename_button.set_tooltip_text("Rename playlist")
    rename_icon = Gtk.Image.new_from_icon_name(rename_icon_name)
    rename_icon.set_pixel_size(16)
    rename_button.set_child(rename_icon)
    rename_button.set_valign(Gtk.Align.CENTER)
    rename_button.set_sensitive(False)
    rename_button.connect(
        "clicked", lambda button: playlist_manager.on_playlist_rename_clicked(app, button)
    )

    read_only_badge = Gtk.Label(label="Read-only")
    read_only_badge.add_css_class("playlist-readonly-badge")
    read_only_badge.set_visible(False)

    title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    title_row.set_hexpand(True)
    title_row.set_halign(Gtk.Align.FILL)
    title_row.append(title)
    title_row.append(rename_button)
    title_row.append(read_only_badge)

    delete_icon_name = app.pick_icon_name(
        ["user-trash-symbolic", "edit-delete-symbolic", "user-trash"]
    )
    delete_button = Gtk.Button()
    delete_button.add_css_class("playlist-header-button")
    delete_button.add_css_class("playlist-delete-button")
    delete_button.set_tooltip_text("Delete playlist")
    delete_icon = Gtk.Image.new_from_icon_name(delete_icon_name)
    delete_icon.set_pixel_size(16)
    delete_button.set_child(delete_icon)
    delete_button.set_valign(Gtk.Align.START)
    delete_button.set_sensitive(False)
    delete_button.connect(
        "clicked", lambda button: playlist_manager.on_playlist_delete_clicked(app, button)
    )

    title_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    title_bar.set_hexpand(True)
    title_bar.set_halign(Gtk.Align.FILL)
    title_bar.append(title_row)
    title_bar.append(delete_button)

    controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    controls_row.set_halign(Gtk.Align.START)

    play_button = Gtk.Button()
    play_button.add_css_class("suggested-action")
    play_button.add_css_class("detail-play")
    play_button.set_halign(Gtk.Align.START)
    play_button.set_tooltip_text("Play")
    play_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
    play_icon.set_pixel_size(18)
    play_button.set_child(play_icon)
    play_button.set_sensitive(False)
    play_button.set_visible(False)
    play_button.connect("clicked", app.on_playlist_play_clicked)
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
    shuffle_button.connect("clicked", app.on_playlist_shuffle_clicked)
    controls_row.append(shuffle_button)

    info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    info.append(title_bar)
    info.append(controls_row)

    header.append(art)
    header.append(info)
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

    tracks_table = track_table.build_tracks_table(
        app,
        store_attr="playlist_tracks_store",
        sort_model_attr="playlist_tracks_sort_model",
        selection_attr="playlist_tracks_selection",
        view_attr="playlist_tracks_view",
        action_labels=("Play", "Remove from this playlist"),
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

    app.playlist_detail_view = overlay
    app.playlist_detail_background = background
    app.playlist_detail_art = art
    app.playlist_detail_title = title
    app.playlist_detail_status_label = status
    app.playlist_detail_play_button = play_button
    app.playlist_detail_shuffle_button = shuffle_button
    app.playlist_detail_read_only_badge = read_only_badge
    app.playlist_detail_rename_button = rename_button
    app.playlist_detail_delete_button = delete_button
    return overlay
