from gi.repository import Gtk, Pango


def build_output_selector(app) -> Gtk.Widget:
    menu_button = Gtk.MenuButton()
    menu_button.add_css_class("flat")
    menu_button.add_css_class("output-button")
    menu_button.set_tooltip_text(f"Output: {app.output_selected_name}")
    menu_button.set_primary(True)

    icon_name = app.pick_icon_name(
        [
            "computer-symbolic",
            "video-display-symbolic",
            "audio-card-symbolic",
            "multimedia-player-symbolic",
            "audio-speakers-symbolic",
        ]
    )
    button_content = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL, spacing=6
    )
    icon = Gtk.Image.new_from_icon_name(icon_name)
    output_label = Gtk.Label(label=app.output_selected_name)
    output_label.add_css_class("output-label")
    output_label.set_ellipsize(Pango.EllipsizeMode.END)
    output_label.set_single_line_mode(True)
    output_label.set_max_width_chars(18)
    button_content.append(icon)
    button_content.append(output_label)
    menu_button.set_child(button_content)

    popover = Gtk.Popover()
    popover.set_has_arrow(False)
    popover.set_position(Gtk.PositionType.BOTTOM)
    popover.add_css_class("output-popover")
    popover.connect("map", app.on_output_popover_mapped)

    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    container.set_margin_start(6)
    container.set_margin_end(6)
    container.set_margin_top(6)
    container.set_margin_bottom(6)

    title = Gtk.Label(label="Output", xalign=0)
    title.add_css_class("output-title")
    container.append(title)

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.set_activate_on_single_click(True)
    listbox.add_css_class("output-list")
    listbox.connect("row-activated", app.on_output_target_activated)
    container.append(listbox)

    group_label = Gtk.Label(label="Group Players", xalign=0)
    group_label.add_css_class("output-title")
    container.append(group_label)

    group_players_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    group_players_box.add_css_class("output-group-list")
    container.append(group_players_box)

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    container.append(status)

    popover.set_child(container)
    menu_button.set_popover(popover)

    app.output_menu_button = menu_button
    app.output_popover = popover
    app.output_targets_list = listbox
    app.output_group_players_box = group_players_box
    app.output_status_label = status
    app.output_label = output_label

    return menu_button
