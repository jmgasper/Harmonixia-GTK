from gi.repository import Gtk, Pango

from constants import DETAIL_ART_SIZE, DETAIL_ARTIST_AVATAR_SIZE
from ui import track_table


def build_album_detail_section(app) -> Gtk.Widget:
    overlay = Gtk.Overlay()
    overlay.add_css_class("album-detail")
    overlay.set_hexpand(True)
    overlay.set_vexpand(True)

    background = Gtk.Picture()
    background.add_css_class("album-detail-bg")
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
    dimmer.add_css_class("album-detail-dim")
    dimmer.set_hexpand(True)
    dimmer.set_vexpand(True)
    dimmer.set_halign(Gtk.Align.FILL)
    dimmer.set_valign(Gtk.Align.FILL)
    overlay.add_overlay(dimmer)

    detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    detail_box.add_css_class("album-detail-content")
    detail_box.set_hexpand(True)
    detail_box.set_vexpand(True)
    detail_box.set_halign(Gtk.Align.FILL)
    detail_box.set_valign(Gtk.Align.FILL)

    top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    back_button = Gtk.Button()
    back_button.add_css_class("detail-back")
    back_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    back_content.append(Gtk.Image.new_from_icon_name("go-previous-symbolic"))
    back_content.append(Gtk.Label(label="Back"))
    back_button.set_child(back_content)
    back_button.connect("clicked", app.on_album_detail_close)
    top_bar.append(back_button)
    detail_box.append(top_bar)

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

    info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    title = Gtk.Label(label="Album", xalign=0)
    title.add_css_class("detail-title")
    title.set_wrap(True)
    title.set_ellipsize(Pango.EllipsizeMode.END)

    artist_label = Gtk.Label(label="Artist", xalign=0)
    artist_label.add_css_class("detail-artist")
    artist_label.set_wrap(True)
    artist_label.set_ellipsize(Pango.EllipsizeMode.END)

    artist_image = Gtk.Picture()
    artist_image.add_css_class("detail-artist-avatar")
    artist_image.set_size_request(
        DETAIL_ARTIST_AVATAR_SIZE,
        DETAIL_ARTIST_AVATAR_SIZE,
    )
    artist_image.set_halign(Gtk.Align.START)
    artist_image.set_valign(Gtk.Align.CENTER)
    artist_image.set_can_shrink(True)
    artist_image.set_visible(False)
    if hasattr(artist_image, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        artist_image.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(artist_image, "set_keep_aspect_ratio"):
        artist_image.set_keep_aspect_ratio(False)

    artist_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    artist_row.add_css_class("detail-artist-row")
    artist_row.set_halign(Gtk.Align.START)
    artist_row.set_valign(Gtk.Align.CENTER)
    artist_row.append(artist_image)
    artist_row.append(artist_label)

    artist_button = Gtk.Button()
    artist_button.add_css_class("detail-artist-link")
    artist_button.set_has_frame(False)
    artist_button.set_halign(Gtk.Align.START)
    artist_button.set_sensitive(False)
    artist_button.set_child(artist_row)
    artist_button.connect("clicked", app.on_album_detail_artist_clicked)

    release_year_label = Gtk.Label(label="", xalign=0)
    release_year_label.add_css_class("detail-meta")
    release_year_label.add_css_class("detail-release-year")
    release_year_label.set_visible(False)

    track_summary_label = Gtk.Label(label="", xalign=0)
    track_summary_label.add_css_class("detail-meta")
    track_summary_label.add_css_class("detail-track-summary")
    track_summary_label.set_visible(False)

    metadata_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    metadata_box.add_css_class("detail-meta-box")
    metadata_box.set_halign(Gtk.Align.START)
    metadata_box.append(release_year_label)
    metadata_box.append(track_summary_label)

    play_button = Gtk.Button()
    play_button.add_css_class("suggested-action")
    play_button.add_css_class("detail-play")
    play_button.set_halign(Gtk.Align.START)
    play_button.set_tooltip_text("Play")
    play_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
    play_icon.set_pixel_size(18)
    play_button.set_child(play_icon)
    play_button.connect("clicked", app.on_album_play_clicked)

    add_to_queue_button = Gtk.Button()
    add_to_queue_button.add_css_class("detail-queue")
    add_to_queue_button.set_halign(Gtk.Align.START)
    add_to_queue_button.set_tooltip_text("Add to Queue")
    add_to_queue_icon = Gtk.Image.new_from_icon_name("list-add-symbolic")
    add_to_queue_icon.set_pixel_size(18)
    add_to_queue_button.set_child(add_to_queue_icon)
    add_to_queue_button.connect(
        "clicked",
        app.on_album_add_to_queue_clicked,
    )

    add_to_playlist_button = Gtk.Button()
    add_to_playlist_button.add_css_class("detail-playlist")
    add_to_playlist_button.set_halign(Gtk.Align.START)
    add_to_playlist_button.set_tooltip_text("Add to Playlist")
    add_to_playlist_icon = Gtk.Image.new_from_icon_name("playlist-symbolic")
    add_to_playlist_icon.set_pixel_size(18)
    add_to_playlist_button.set_child(add_to_playlist_icon)
    add_to_playlist_button.connect(
        "clicked",
        app.on_album_add_to_playlist_clicked,
    )

    start_radio_button = Gtk.Button()
    start_radio_button.add_css_class("detail-radio")
    start_radio_button.set_halign(Gtk.Align.START)
    start_radio_button.set_tooltip_text("Start Radio")
    start_radio_icon_name = app.pick_icon_name(
        ["radio-symbolic", "radio", "media-playlist-shuffle-symbolic"]
    )
    start_radio_icon = Gtk.Image.new_from_icon_name(
        start_radio_icon_name
    )
    start_radio_icon.set_pixel_size(18)
    start_radio_button.set_child(start_radio_icon)
    start_radio_button.connect(
        "clicked",
        app.on_album_start_radio_clicked,
    )

    controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    controls_row.set_halign(Gtk.Align.START)
    controls_row.append(play_button)
    controls_row.append(add_to_queue_button)
    controls_row.append(add_to_playlist_button)
    controls_row.append(start_radio_button)

    info.append(title)
    info.append(artist_button)
    info.append(metadata_box)
    info.append(controls_row)

    header.append(art)
    header.append(info)
    detail_box.append(header)

    tracks_label = Gtk.Label(label="Tracks")
    tracks_label.add_css_class("section-title")
    tracks_label.add_css_class("detail-tracks-title")
    tracks_label.set_xalign(0)
    detail_box.append(tracks_label)

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    detail_box.append(status)

    tracks_table = track_table.build_tracks_table(
        app,
        include_album_column=False,
    )
    tracks_scroller = Gtk.ScrolledWindow()
    tracks_scroller.set_policy(
        Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
    )
    tracks_scroller.set_child(tracks_table)
    if hasattr(tracks_scroller, "set_propagate_natural_height"):
        tracks_scroller.set_propagate_natural_height(True)
    tracks_scroller.set_vexpand(False)
    detail_box.append(tracks_scroller)

    overlay.add_overlay(detail_box)

    app.album_detail_view = overlay
    app.album_detail_background = background
    app.album_detail_art = art
    app.album_detail_title = title
    app.album_detail_artist = artist_label
    app.album_detail_artist_image = artist_image
    app.album_detail_artist_button = artist_button
    app.album_detail_release_year = release_year_label
    app.album_detail_track_summary = track_summary_label
    app.album_detail_status_label = status
    app.album_detail_play_button = play_button
    app.album_detail_add_to_queue_button = add_to_queue_button
    app.album_detail_add_to_playlist_button = add_to_playlist_button
    app.album_detail_start_radio_button = start_radio_button
    return overlay
