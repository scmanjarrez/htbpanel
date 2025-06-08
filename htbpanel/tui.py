import json
import subprocess

from textual.app import App, ComposeResult, SystemCommand
from textual.containers import (
    Center,
    Container,
    Horizontal,
    Vertical,
    VerticalScroll,
)
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    RadioButton,
    RadioSet,
    Select,
    SelectionList,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets._toggle_button import ToggleButton
from textual.widgets.tabbed_content import ContentTabs

import htbpanel.htbapi as api

ACTIVE = {}


class BoxLabel(Static):
    def __init__(self, title, subtitle=""):
        self.BORDER_TITLE = title
        self.BORDER_SUBTITLE = subtitle
        classes = "" if ACTIVE else "unknown-container"
        super().__init__(
            content=ACTIVE[title.lower()] if ACTIVE else "?",
            classes=classes,
            id=title.lower(),
        )


class FlagStatus(ToggleButton):
    BUTTON_LEFT = ""
    BUTTON_RIGHT = ""

    def __init__(self, flag_type):
        super().__init__(
            id=flag_type,
            value=self.update_icon(flag_type),
            label=flag_type.capitalize(),
            disabled=True,
            button_first=False,
            classes="" if ACTIVE else "unknown-container-button",
        )

    def update_icon(self, flag_type):
        self.BUTTON_INNER = "?"
        owned = False
        if ACTIVE:
            owned = ACTIVE[f"{flag_type}_own"]
            self.BUTTON_INNER = "✓" if owned else "X"
        return owned


class FlagInput(Input):
    def __init__(self, name: str):
        super().__init__(
            placeholder=name.capitalize(),
            id=name,
            restrict=r"[a-zA-Z0-9]*",
            max_length=32,
            disabled=not ACTIVE,
        )


class BoxAction(Button):
    def __init__(self, name: str):
        icon = "⏵"
        variant = "success"
        classes = "action-button"
        disabled = False
        match name:
            case "start":
                classes = f"{classes} {'invisible' if ACTIVE else ''}"
            case "stop":
                icon = "■"
                variant = "error"
                classes = f"{classes} {'' if ACTIVE else 'invisible'}"
            case "reset":
                icon = "↻"
                variant = "warning"
                disabled = not ACTIVE
            case "download":
                icon = "⤓"
                classes = f"{classes} download"
        super().__init__(
            icon,
            id=name,
            variant=variant,
            disabled=disabled,
            classes=classes,
        )


class FilterScreen(ModalScreen):
    BINDINGS = [("q", "cancel", "Cancel")]

    class CrossRadioButton(RadioButton):
        BUTTON_INNER = "X"

    def compose(self):
        with Container(classes="modal"):
            with Container(classes="filters-type-container"):
                with Container():
                    with Container(classes="filter-status-container"):
                        with Center():
                            yield Static("Status", classes="welcome")
                        yield RadioSet(
                            *[
                                self.CrossRadioButton(k, value=v)
                                for k, v in self.status_types
                            ],
                            id="filter-status",
                        )
                    with Container(classes="filter-availability-container"):
                        with Center():
                            yield Static("Availability", classes="welcome")
                        yield SelectionList(
                            *self.availability_types,
                            classes="filter-availability",
                            id="filter-availability",
                        )
                with Container():
                    with Center():
                        yield Static("Difficulty", classes="welcome")
                    yield SelectionList(
                        *self.difficulty_types,
                        classes="filter-select",
                        id="filter-difficulty",
                    )
                with Container():
                    with Center():
                        yield Static("OS", classes="welcome")
                    yield SelectionList(
                        *self.os_types, classes="filter-select", id="filter-os"
                    )
                with Container():
                    with Center():
                        yield Static("Category", classes="welcome")
                    yield SelectionList(
                        *self.category_types,
                        classes="filter-select",
                        id="filter-category",
                    )
                with Container():
                    with Center():
                        yield Static("Area of Interest", classes="welcome")
                    yield SelectionList(
                        *self.area_types,
                        classes="filter-select",
                        id="filter-area",
                    )
                with Container():
                    with Center():
                        yield Static("Vulnerabilities", classes="welcome")
                    yield SelectionList(
                        *self.vulnerability_types,
                        classes="filter-select",
                        id="filter-vulnerability",
                    )
            with Center(classes="filters-button-container"):
                yield Button(
                    "Cancel",
                    variant="error",
                    classes="action-button",
                    compact=True,
                    id="filter-cancel",
                )
                yield Button(
                    "Accept",
                    variant="success",
                    classes="action-button",
                    compact=True,
                    id="filter-ok",
                )

    def on_button_pressed(self, event):
        match event.button.id:
            case "filter-cancel":
                self.dismiss({})
            case "filter-ok":
                self.dismiss(
                    {
                        "status": self.selected("filter-status"),
                        "availability": self.selected("filter-availability"),
                        "difficulty": self.selected("filter-difficulty"),
                        "os": self.selected("filter-os"),
                        "category": self.selected("filter-category"),
                        "area": self.selected("filter-area"),
                        "vulnerability": self.selected("filter-vulnerability"),
                    }
                )

    def selected(self, widget_id):
        w = self.query_one(f"#{widget_id}")
        if widget_id == "filter-status":
            return w.pressed_button.label.plain
        return [
            w.get_option_at_index(w._values[s]).prompt.plain for s in w.selected
        ]

    def action_cancel(self):
        self.dismiss({})


class HTBPanel(App):
    CSS_PATH = "css/app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f", "flag", "Flag"),
        ("ctrl+r", "reset", "Reset"),
        ("ctrl+s", "stop", "Stop"),
        ("s", "search", "Search"),
        ("r", "reload", "Reload"),
        ("1", "active", "ActiveTab"),
        ("2", "machines", "MachinesTab"),
        ("ctrl+f", "filters", "Filters"),
        ("Esc", "escape", "Exit field"),
        ("Enter", "submit", "Submit"),
    ]
    ENABLE_COMMAND_PALETTE = False
    tab = reactive("pane-active", bindings=True)

    def __init__(self, client, db, info):
        super().__init__()
        self.client = client
        self.db = db
        self.info = info
        self.mounted = False
        self.cnt = 0
        self.prepare_data()

    def prepare_data(self):
        self.update_active()
        self.vpn_types = self.db.vpn_list()
        self.machine_types = self.db.machines_by_vip(self.info["user"]["vip"])

    def compose(self):
        with TabbedContent(classes="border", id="tab-container"):
            with TabPane("Active machine", id="pane-active", classes="border"):
                with Center():
                    yield Static(
                        f"Welcome, {self.info['user']['name']}!",
                        classes="border welcome",
                    )
                with Container(classes="border info-machine"):
                    yield BoxLabel("Name")
                    yield BoxLabel(
                        "IP",
                        "Copy",
                    )
                    yield BoxLabel("OS")
                    yield BoxLabel("Difficulty")
                with Container(classes="border info-flags-container"):
                    with Container(classes="flags-container"):
                        yield Static("Flags:")
                        yield FlagStatus("user")
                        yield FlagStatus("root")
                    yield FlagInput("flag")
                with Container(classes="border machine-buttons-container"):
                    yield BoxAction("start")
                    yield BoxAction("stop")
                    yield BoxAction("reset")
                    yield Select(
                        self.machine_types,
                        value=self.machine_types[0][1]
                        if not ACTIVE
                        else ACTIVE["id"],
                        id="machine",
                        allow_blank=False,
                    )
                    # yield Select(
                    #     self.vpn_types,
                    #     value=self.info["current_vpn"]["id"],
                    #     id="vpn",
                    #     allow_blank=False,
                    # )
                    # yield BoxAction("download")
            with TabPane(
                "Machine list", id="pane-machines", classes="border-no-bottom"
            ):
                with Container(classes="border-no-top search-container"):
                    yield Input(placeholder="Search", id="search")
                    yield Button(
                        "Filters", variant="primary", id="filters-button"
                    )
                with Container():
                    yield DataTable()
        yield Footer()

    def on_mount(self):
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Machine", "Difficulty", "OS", "Free", "Tags")
        table.add_rows(self.db.machines_with_tags())
        filter_screen = FilterScreen()
        filter_screen.status_types = (
            ("Complete", False),
            ("Incomplete", False),
            ("Both", True),
        )
        filter_screen.availability_types = [
            (d, idx) for idx, d in enumerate(["Free", "Active"])
        ]
        filter_screen.difficulty_types = [
            (d, idx)
            for idx, d in enumerate(["Easy", "Medium", "Hard", "Insane"])
        ]
        filter_screen.os_types = self.db.machines_os_list()
        filter_screen.category_types = self.db.tags_category_list()
        filter_screen.area_types = self.db.tags_area_list()
        filter_screen.vulnerability_types = self.db.tags_vulnerability_list()
        self.install_screen(filter_screen, name="filters")
        self.update_active()
        self.mounted = True

    def key_ctrl_c(self):
        self.app.exit()

    def on_button_pressed(self, event):
        if event.button.id == "filters-button":
            self.push_screen("filters", self.on_filters_accept)
        elif event.button.id in ["cancel", "accept"]:
            self.pop_screen()

    def check_action(self, action, _) -> bool:
        if isinstance(self.app.focused, FlagInput) or isinstance(
            self.app.focused, Input
        ):
            if action in ["escape", "submit"]:
                return True
        else:
            if self.tab == "pane-active":
                if action in ["escape", "submit", "active", "filters"]:
                    return False
                return True
            else:
                if action in ["escape", "submit", "machines", "stop", "reset"]:
                    return False
                return True
        return False

    def action_flag(self):
        self.query_one("#flag").focus()

    def action_search(self):
        self.query_one("#search").focus()

    def action_filters(self):
        self.push_screen("filters", self.on_filters_accept)

    def action_machines(self):
        self.query_one("#tab-container").active = "pane-machines"
        self.tab = "pane-machines"
        self.set_focus(self.query_one(ContentTabs))

    def action_active(self):
        self.query_one("#tab-container").active = "pane-active"
        self.tab = "pane-active"
        self.set_focus(self.query_one(ContentTabs))

    def action_show_tab(self, tab):
        self.query_one("#tab-container").active = tab
        self.tab = tab

    def on_tabbed_content_tab_activated(self, event):
        self.tab = event.tabbed_content.active

    def on_click(self, event):
        if event.widget.id == "ip":
            if not subprocess.call(
                ["which", "xclip"], stdout=subprocess.DEVNULL
            ):
                xclip = subprocess.Popen(
                    ["xclip", "-sel", "cl"], stdin=subprocess.PIPE
                )
                xclip.communicate(event.widget.renderable.encode())

    def key_escape(self):
        if isinstance(self.app.screen, FilterScreen):
            self.pop_screen()
        else:
            self.set_focus(self.query_one(ContentTabs))

    def on_filters_accept(self, data):
        if data:
            # self.notify(json.dumps(list(data.keys())))
            table = self.query_one(DataTable)
            table.clear()
            table.add_rows(self.db.machines_by_filters(data))

    async def action_reload(self):
        self.info.update(await api.query_current_box(self.client))
        self.info.update(await api.query_current_vpn(self.client))
        self.cnt += 1
        self.update_active()

    def update_active(self):
        active = self.info["current_box"] is not None
        if self.cnt == 1:
            active = False
        if active:
            ACTIVE.update(self.info["current_box"])
        else:
            ACTIVE.clear()
        # self.notify(f"status: {active}")
        if self.mounted and active:
            # Show stop
            stop_btn = self.query_one("#stop")
            stop_btn.remove_class("invisible")
            # Hide start
            start_btn = self.query_one("#start")
            start_btn.add_class("invisible")
            # Update reset disabled status
            reset_btn = self.query_one("#reset")
            reset_btn.disabled = False
            # Update user/root flag status and color
            for flag_type in ["user", "root"]:
                flag_btn = self.query_one(f"#{flag_type}")
                flag_btn.remove_class("unknown-container-button")
                flag_btn.value = flag_btn.update_icon(flag_type)
            # Enable flag input
            flag_in = self.query_one("#flag")
            flag_in.disabled = False
            # Update box information
            for box_type in ["name", "ip", "os", "difficulty"]:
                box_label = self.query_one(f"#{box_type}")
                box_label.remove_class("unknown-container")
                box_label.update(ACTIVE[box_type])
            # Set machine select to current box
            machine_sel = self.query_one("#machine")
            machine_sel.value = ACTIVE["id"]
        elif self.mounted and not active:
            # Hide stop
            stop_btn = self.query_one("#stop")
            stop_btn.add_class("invisible")
            # Show start
            start_btn = self.query_one("#start")
            start_btn.remove_class("invisible")
            # Update reset disabled status
            reset_btn = self.query_one("#reset")
            reset_btn.disabled = True
            # Update user/root flag status and color
            for flag_type in ["user", "root"]:
                flag_btn = self.query_one(f"#{flag_type}")
                flag_btn.add_class("unknown-container-button")
                flag_btn.value = flag_btn.update_icon(flag_type)
            # Disable flag input
            flag_in = self.query_one("#flag")
            flag_in.disabled = True
            # Remove box information
            for box_type in ["name", "ip", "os", "difficulty"]:
                box_label = self.query_one(f"#{box_type}")
                box_label.add_class("unknown-container")
                box_label.update("?")
