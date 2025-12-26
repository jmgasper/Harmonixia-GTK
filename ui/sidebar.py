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
    for item, view_name in [("Albums", "albums"), ("Artists", "artists")]:
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
    if hasattr(now_playing_art, "set_content_fit") and hasattr(
        Gtk, "ContentFit"
    ):
        now_playing_art.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(now_playing_art, "set_keep_aspect_ratio"):
        now_playing_art.set_keep_aspect_ratio(True)
    click_gesture = Gtk.GestureClick.new()
    click_gesture.connect("released", app.on_now_playing_art_clicked)
    now_playing_art.add_controller(click_gesture)
    app.sidebar_now_playing_art = now_playing_art

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
