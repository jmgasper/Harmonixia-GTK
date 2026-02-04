from gi.repository import Gtk

from constants import SIDEBAR_WIDTH, SIDEBAR_ART_SIZE, SIDEBAR_ACTION_MARGIN


def build_sidebar(app) -> Gtk.Widget:
    from ui import playlist_manager, settings_panel

    sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    home_list = Gtk.ListBox()
    home_list.add_css_class("sidebar-list")
    home_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    home_list.connect(
        "row-selected",
        lambda listbox, row: on_library_selected(app, listbox, row),
    )
    home_row = make_sidebar_row("Home")
    home_row.add_css_class("sidebar-primary")
    home_row.view_name = "home"
    home_list.append(home_row)
    home_list.select_row(home_row)
    home_list.set_margin_top(8)
    home_list.set_margin_bottom(8)
    sidebar.append(home_list)
    app.home_nav_list = home_list

    library_label = Gtk.Label(label="Library")
    library_label.add_css_class("section-title")
    library_label.set_xalign(0)
    sidebar.append(library_label)

    library_list = Gtk.ListBox()
    library_list.add_css_class("sidebar-list")
    library_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    library_list.connect(
        "row-selected",
        lambda listbox, row: on_library_selected(app, listbox, row),
    )
    app.library_list = library_list
    library_rows = []
    for item, view_name in [
        ("Albums", "albums"),
        ("Artists", "artists"),
        ("Favorites", "favorites"),
    ]:
        row = make_sidebar_row(item)
        row.view_name = view_name
        library_list.append(row)
        library_rows.append(row)
    sidebar.append(library_list)

    playlists_header = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=6,
    )
    playlists_header.add_css_class("sidebar-section-header")
    playlists_header.set_hexpand(True)
    playlists_header.set_halign(Gtk.Align.FILL)
    playlists_label = Gtk.Label(label="Playlists")
    playlists_label.add_css_class("section-title")
    playlists_label.set_xalign(0)
    playlists_label.set_hexpand(True)
    playlists_header.append(playlists_label)

    playlists_add = Gtk.Button()
    playlists_add.add_css_class("playlist-add-button")
    playlists_add.set_tooltip_text("Create playlist")
    playlists_add.set_child(Gtk.Image.new_from_icon_name("list-add-symbolic"))
    playlists_add.connect(
        "clicked",
        lambda button: playlist_manager.on_playlist_add_clicked(app, button),
    )
    playlists_header.append(playlists_add)
    sidebar.append(playlists_header)

    playlists_list = Gtk.ListBox()
    playlists_list.add_css_class("sidebar-list")
    playlists_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    playlists_list.connect(
        "row-selected",
        lambda listbox, row: playlist_manager.on_playlist_selected(
            app, listbox, row
        ),
    )
    sidebar.append(playlists_list)

    playlists_status = Gtk.Label()
    playlists_status.add_css_class("status-label")
    playlists_status.set_xalign(0)
    playlists_status.set_wrap(True)
    playlists_status.set_visible(False)
    sidebar.append(playlists_status)

    app.playlists_list = playlists_list
    app.playlists_status_label = playlists_status
    app.playlists_add_button = playlists_add
    playlist_manager.refresh_playlists(app)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(sidebar)
    scroller.set_vexpand(True)

    now_playing_art = Gtk.Picture()
    now_playing_art.add_css_class("sidebar-now-playing-art")
    now_playing_art.set_size_request(SIDEBAR_ART_SIZE, SIDEBAR_ART_SIZE)
    now_playing_art.set_halign(Gtk.Align.FILL)
    now_playing_art.set_valign(Gtk.Align.CENTER)
    now_playing_art.set_hexpand(True)
    now_playing_art.set_vexpand(False)
    now_playing_art.set_margin_bottom(4)
    now_playing_art.set_tooltip_text("Now Playing")
    now_playing_art.set_can_shrink(True)
    now_playing_art.set_visible(False)
    if hasattr(now_playing_art, "set_content_fit") and hasattr(
        Gtk, "ContentFit"
    ):
        now_playing_art.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(now_playing_art, "set_keep_aspect_ratio"):
        now_playing_art.set_keep_aspect_ratio(True)
    click_gesture = Gtk.GestureClick.new()
    click_gesture.set_button(1)
    click_gesture.connect("released", app.on_now_playing_art_clicked)
    now_playing_art.add_controller(click_gesture)
    context_gesture = Gtk.GestureClick.new()
    context_gesture.set_button(3)
    context_gesture.connect("pressed", app.on_now_playing_art_context_menu)
    now_playing_art.add_controller(context_gesture)
    app.sidebar_now_playing_art = now_playing_art

    now_playing_popover = Gtk.Popover()
    now_playing_popover.set_has_arrow(False)
    now_playing_popover.add_css_class("track-action-popover")

    action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    action_box.set_margin_start(6)
    action_box.set_margin_end(6)
    action_box.set_margin_top(6)
    action_box.set_margin_bottom(6)

    action_buttons = []
    for label in ("Add to existing playlist", "Add to new playlist"):
        action_button = Gtk.Button(label=label)
        action_button.set_halign(Gtk.Align.FILL)
        action_button.set_hexpand(True)
        action_button.add_css_class("track-action-item")
        action_button.connect(
            "clicked", app.on_track_action_clicked, now_playing_popover, label
        )
        action_box.append(action_button)
        action_buttons.append(action_button)

    now_playing_popover.set_child(action_box)
    now_playing_popover.set_parent(now_playing_art)
    app.sidebar_now_playing_popover = now_playing_popover
    app.sidebar_now_playing_action_buttons = action_buttons

    repeat_icon_name = app.pick_icon_name(
        ["media-playlist-repeat-symbolic", "media-playlist-repeat"]
    )
    repeat_one_icon_name = app.pick_icon_name(
        [
            "media-playlist-repeat-song-symbolic",
            "media-playlist-repeat-song",
            "media-playlist-repeat-one-symbolic",
        ]
    )
    shuffle_icon_name = app.pick_icon_name(
        ["media-playlist-shuffle-symbolic", "media-playlist-shuffle"]
    )

    queue_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    queue_controls.add_css_class("queue-controls")
    queue_controls.set_halign(Gtk.Align.FILL)
    queue_controls.set_hexpand(True)
    queue_controls.set_homogeneous(True)
    queue_controls.set_margin_bottom(2)
    queue_controls.set_visible(False)

    repeat_button = Gtk.Button()
    repeat_button.add_css_class("queue-toggle")
    repeat_button.set_tooltip_text("Repeat off")
    repeat_stack = Gtk.Stack()
    repeat_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    repeat_stack.set_transition_duration(150)
    repeat_icon = Gtk.Image.new_from_icon_name(repeat_icon_name)
    repeat_spinner = Gtk.Spinner()
    repeat_spinner.set_size_request(16, 16)
    repeat_stack.add_named(repeat_icon, "icon")
    repeat_stack.add_named(repeat_spinner, "spinner")
    repeat_stack.set_visible_child_name("icon")
    repeat_button.set_child(repeat_stack)
    repeat_button.connect("clicked", app.on_repeat_clicked)

    shuffle_button = Gtk.Button()
    shuffle_button.add_css_class("queue-toggle")
    shuffle_button.set_tooltip_text("Shuffle off")
    shuffle_stack = Gtk.Stack()
    shuffle_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    shuffle_stack.set_transition_duration(150)
    shuffle_icon = Gtk.Image.new_from_icon_name(shuffle_icon_name)
    shuffle_spinner = Gtk.Spinner()
    shuffle_spinner.set_size_request(16, 16)
    shuffle_stack.add_named(shuffle_icon, "icon")
    shuffle_stack.add_named(shuffle_spinner, "spinner")
    shuffle_stack.set_visible_child_name("icon")
    shuffle_button.set_child(shuffle_stack)
    shuffle_button.connect("clicked", app.on_shuffle_clicked)

    queue_controls.append(repeat_button)
    queue_controls.append(shuffle_button)

    app.sidebar_queue_controls = queue_controls
    app.repeat_button = repeat_button
    app.repeat_button_stack = repeat_stack
    app.repeat_button_icon = repeat_icon
    app.repeat_button_spinner = repeat_spinner
    app.shuffle_button = shuffle_button
    app.shuffle_button_stack = shuffle_stack
    app.shuffle_button_icon = shuffle_icon
    app.shuffle_button_spinner = shuffle_spinner
    app.repeat_all_icon_name = repeat_icon_name
    app.repeat_one_icon_name = repeat_one_icon_name
    app.shuffle_icon_name = shuffle_icon_name
    app.update_queue_controls()

    settings_button = Gtk.Button()
    settings_button.add_css_class("sidebar-action")
    settings_button.set_tooltip_text("Settings")
    settings_button.set_hexpand(True)
    settings_button.set_halign(Gtk.Align.FILL)
    settings_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    settings_icon = Gtk.Image.new_from_icon_name(
        "preferences-system-symbolic"
    )
    settings_label = Gtk.Label(label="Settings", xalign=0)
    settings_content.append(settings_icon)
    settings_content.append(settings_label)
    settings_button.set_child(settings_content)
    settings_button.connect(
        "clicked",
        lambda button: settings_panel.on_settings_clicked(app, button),
    )
    app.settings_button = settings_button

    action_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    action_area.set_margin_top(SIDEBAR_ACTION_MARGIN)
    action_area.set_margin_bottom(SIDEBAR_ACTION_MARGIN)
    action_area.set_margin_start(SIDEBAR_ACTION_MARGIN)
    action_area.set_margin_end(SIDEBAR_ACTION_MARGIN)
    action_area.append(now_playing_art)
    action_area.append(queue_controls)
    action_area.append(settings_button)

    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    container.add_css_class("sidebar")
    container.set_size_request(SIDEBAR_WIDTH, -1)
    container.append(scroller)
    container.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))
    container.append(action_area)
    return container


def on_library_selected(
    app,
    listbox: Gtk.ListBox,
    row: Gtk.ListBoxRow | None,
) -> None:
    if not row or not app.main_stack:
        return
    view_name = getattr(row, "view_name", None)
    if view_name:
        app.main_stack.set_visible_child_name(view_name)
    if listbox is app.library_list and app.home_nav_list:
        app.home_nav_list.unselect_all()
    elif listbox is app.home_nav_list and app.library_list:
        app.library_list.unselect_all()
    if app.playlists_list:
        app.playlists_list.unselect_all()


def make_sidebar_row(text: str) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    label = Gtk.Label(label=text, xalign=0)
    label.set_margin_top(2)
    label.set_margin_bottom(2)
    row.set_child(label)
    return row
