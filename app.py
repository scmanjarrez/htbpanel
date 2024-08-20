import os
import sys
import httpx
import time
import json
from collections import defaultdict
from typing import Any
from pprint import pprint
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Center, Vertical, Container, VerticalScroll, Grid
from textual.reactive import reactive
from textual import events, log
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, TabbedContent, TabPane, Static, Input, Select, SelectionList, RadioSet, RadioButton, Checkbox, DataTable
from textual.widgets.tabbed_content import ContentTabs



TOKEN = ""
API = "https://labs.hackthebox.com/api/v4"
FILES = {
    "info": "info_cache.json",
    "mach": "machines_cache.json",
    "tags": "tags_cache.json"
}
INFO: dict[str, dict] = {}
MACH: dict[str, dict] = {}
TAGS: dict[str, dict] = {}
DATA = {}


def flag_status(flag: str) -> tuple[str, str]:
    if active_machine():
        return ("x", "error") if INFO["mach"][f"{flag}_own"] else ("✓", "success")
    return "?", "primary"


def active_machine() -> bool:
    return "mach" in INFO


def machine_action(machine: int, action: str) -> bool:
    if action == "spawn":
        res = cl.post(f"{API}/machine/play/{machine}")
    elif action == "stop":
        res = cl.post(f"{API}/machine/stop")
    else:
        res = cl.post(f"{API}/vm/reset", json={"machine_id": machine})
    if res.status_code == 200:
        return True
    return False


def submit_flag(flag: str) -> bool:
    res = cl.post(f"{API}/machine/own",
                    json={"id": INFO["mach"]["id"], "flag": flag})
    if res.status_code == 200:
        return True
    return False

# {'id': 357,
#  'is_starting_point': False,
#  'machine_completed': None,
#  'machine_pwned': False,
#  'message': 'Intelligence user is now owned.',
#  'own_type': 'user',
#  'status': 200,
#  'success': True,
#  'user_rank': {'changed': False, 'newRank': {'id': 4, 'text': None}}}

# {'id': 357,
#  'is_starting_point': False,
#  'machine_completed': None,
#  'machine_pwned': True,
#  'message': 'Intelligence root is now owned.',
#  'own_type': 'root',
#  'status': 200,
#  'success': True,
#  'user_rank': {'changed': False, 'newRank': {'id': 4, 'text': None}}

def prepare_gui_data():
    # Prepare VPN Select data
    DATA["vpn_curr"] = INFO["vpn"]["current"][1]
    DATA["vpn_opts"] = []
    for k, v in INFO["vpn"]["all"].items():
        DATA["vpn_opts"].append((k, v))
    # Prepare TAGS SelectionList data
    DATA["status"] = [
        "Complete",
        "Incomplete",
        "Both",
    ]
    DATA["difficulty"] = [
        ("Easy", 0),
        ("Medium", 1),
        ("Hard", 2),
        ("Insane", 3),
    ]
    DATA["os"] = [
        (name, idx) for idx, name in enumerate(sorted(MACH["by_os"].keys()))
    ]
    DATA["vulnerabilities"] = [
        (name, idx) for idx, name in enumerate(
            sorted(TAGS["Vulnerabilities"].keys())
        )
    ]
    DATA["area"] = [
        (name, idx) for idx, name in enumerate(
            sorted(TAGS["Area of Interest"].keys())
        )
    ]
    DATA["category"] = [
        (name, idx) for idx, name in enumerate(sorted(TAGS["Category"].keys()))
    ]


def retrieve_tags() -> None:
    for m_name in MACH["by_status"]["retired"]:
        res = cl.get(f"{API}/machine/tags/{MACH['by_name'][m_name][0]}")
        if res.status_code == 200:
            data = res.json()["info"]
            TAGS["by_machine"][m_name] = []
            for tag in data:
                if tag["category"] not in TAGS:
                    TAGS[tag["category"]] = {}
                if tag["name"] not in TAGS[tag["category"]]:
                    TAGS[tag["category"]][tag["name"]] = set()
                TAGS[tag["category"]][tag["name"]].add(m_name)
                TAGS["by_machine"][m_name].append(tag["name"])
        else:
            print(res.text)
            print(m_name)
        time.sleep(2)


def process_machines(data: dict[str, list[dict[str, Any]]]) -> None:
    for mach in data["data"]:
        m_name = mach["name"]
        m_id = mach["id"]
        m_diff = mach["difficultyText"]
        m_os = mach["os"]
        m_status = "free" if mach["free"] else "retired"
        MACH["by_name"][m_name] = (m_id, m_diff, m_os, m_status)
        MACH["by_difficulty"][m_diff].append(m_name)
        MACH["by_os"][m_os].append(m_name)
        MACH["by_status"][m_status].append(m_name)



def retrieve_machines(retired: bool = False) -> None:
    target = ""
    if retired:
        target = "list/retired/"
    res = cl.get(f"{API}/machine/{target}paginated",
                   params={"per_page": 100})
    if res.status_code == 200:
        data = res.json()
        pages = data["meta"]["last_page"]
        process_machines(data)
        for page in range(2, pages + 1):
            res = cl.get(f"{API}/machine/{target}paginated",
                           params={"per_page": 100, "page": page})
            if res.status_code == 200:
                data = res.json()
                process_machines(data)
            time.sleep(1)


def retrieve_current_vpn() -> None:
    res = cl.get(f"{API}/connection/status")
    if res.status_code == 200:
        try:
            data = res.json()[0]
            INFO["vpn"]["current"] = (
                data["server"]["friendly_name"], data["server"]["id"]
            )
            INFO["vpn"]["extra"] = (
                f"{data['server']['hostname']}:{data['server']['port']}",
                data["connection"]["ip4"]
            )
        except IndexError:
            INFO["vpn"]["current"] = INFO["vpn"]["def"]


def retrieve_vpn_servers() -> None:
    res = cl.get(f"{API}/connections/servers", params={"product": "release_arena"})
    if res.status_code == 200:
        data = res.json()["data"]
        INFO["vpn"] = {}
        INFO["vpn"]["all"] = {}
        for region in data["options"].values():
            for info in region.values():
                for server in info["servers"].values():
                    INFO["vpn"]["all"][server["friendly_name"]] = server["id"]
        INFO["vpn"]["def"] = (data["assigned"]["friendly_name"], data["assigned"]["id"])


def switch_vpn(vpn: int) -> None:
    res = cl.post(f"{API}/connections/servers/switch/{vpn}")
    if res.status_code == 200:
        ovpn = cl.get(f"{API}/access/ovpnfile/{vpn}/0")
        if ovpn.status_code == 200:
            with open(f"lab_{INFO['user']['name']}.ovpn", "w") as f:
                f.write(ovpn.text)


def retrieve_info_machine() -> None:
    res = cl.get(f"{API}/machine/profile/{INFO['mach']['name']}")
    if res.status_code == 200:
        data = res.json()["info"]
        INFO["mach"]["difficulty"] = data["difficultyText"]
        INFO["mach"]["os"] = data["os"]
        INFO["mach"]["user_own"] = data["authUserInUserOwns"]
        INFO["mach"]["root_own"] = data["authUserInRootOwns"]
        if INFO["mach"]["ip"] is None:
            INFO["mach"]["ip"] = data["ip"]


# This only returns IP for VIP(+?) machine
def retrieve_current_machine() -> None:
    res = cl.get(f"{API}/machine/active")
    if res.status_code == 200:
        data = res.json()["info"]
        if data is not None:
            INFO["mach"] = {
                "name": data["name"],
                "id": data["id"],
                "ip": data["ip"]
            }


def retrieve_user_info() -> None:
    res = cl.get(f"{API}/user/info")
    if res.status_code == 200:
        data = res.json()["info"]
        INFO["user"] = {
            "name": data["name"],
            "id": data["id"],
            "vip": data["canAccessVIP"]
        }


def load_cache(target: str = "info") -> None:
    global INFO, MACH, TAGS
    try:
        with open(FILES[target]) as f:
            if target == "info":
                INFO = json.load(f)
            elif target == "mach":
                MACH = json.load(f)
            else:
                TAGS = json.load(f)
    except FileNotFoundError:
        pass


def save_cache(target: str = "info") -> None:
    def set_default(obj):
        if isinstance(obj, set):
            return list(obj)
        raise TypeError
    with open(FILES[target], "w") as f:
        if target == "info":
            json.dump(INFO, f, indent=2)
        elif target == "mach":
            json.dump(MACH, f, indent=2)
        else:
            json.dump(TAGS, f, indent=2, default=set_default)


class InputFlag(Input):
    def __init__(self, name: str) -> None:
        super().__init__(
            placeholder=name.capitalize(), id=name,
            restrict=r"[a-zA-Z0-9]*", max_length=32,
            disabled=not active_machine())


class ButtonAction(Button):
    def __init__(self, name: str) -> None:
        icon = "↻"
        variant = "warning"
        disabled = not active_machine()
        classes = "action-button"
        if name == "stop":
            icon = "■"
            variant = "error"
        elif name == "download":
            icon = "⤓"
            variant = "success"
            disabled = False
            classes = f"{classes} download"
        super().__init__(icon, variant=variant,
                         disabled=disabled, classes=classes)


class ButtonFlag(Button):
    def __init__(self, name: str) -> None:
        icon, variant = flag_status(name)
        super().__init__(icon, id=name, variant=variant, disabled=True)


class LabelInfo(Static):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__(classes="" if active_machine() else "disabled")
        self.title = title
        self.text = INFO["mach"][title.lower()] if active_machine() else "?"
        self.subtitle = subtitle

    def on_mount(self) -> None:
        self.update(self.text)
        self.border_title = self.title
        if self.subtitle:
            self.border_subtitle = self.subtitle


class CrossRadioButton(RadioButton):
    BUTTON_INNER = 'X'


class FilterScreen(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        with Container(id="test"):
            with Container(id="filters-type-box", classes="box"):
                with Container():
                    with Center():
                        yield Static("Status", classes="label")
                    yield RadioSet(*[CrossRadioButton(bt) for bt in DATA["status"]],
                                   id="status-radio")
                with Container():
                    with Center():
                        yield Static("Difficulty", classes="label")
                    yield SelectionList[int](*DATA["difficulty"],
                                             classes="filter-select")
                with Container():
                    with Center():
                        yield Static("OS", classes="label")
                    yield SelectionList[int](*DATA["os"],
                                             classes="filter-select")
                with Container():
                    with Center():
                        yield Static("Category", classes="label")
                    yield SelectionList[int](*DATA["category"],
                                             classes="filter-select")
                with Container():
                    with Center():
                        yield Static("Area of Interest", classes="label")
                    yield SelectionList[int](*DATA["area"],
                                             classes="filter-select")
                with Container():
                    with Center():
                        yield Static("Vulnerabilities", classes="label")
                    yield SelectionList[int](*DATA["vulnerabilities"],
                                             classes="filter-select")
            with Center(id="filters-actions-box"):
                yield Button("Cancel", variant="error", classes="action-button")
                yield Button("Accept", variant="success", classes="action-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(True)
        else:
            self.dismiss(False)


class CtrlFooter(Footer):
    ctrl_to_caret = False


class HTBPanel(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f", "flag", "Flag"),
        ("ctrl+r", "reset", "Reset"),
        ("ctrl+s", "stop", "Stop"),
        ("s", "search", "Search"),
        ("1", "active", "First tab"),
        ("2", "machines", "Second tab"),
        ("ctrl+f", "filters", "Filters"),
        ("Esc", "escape", "Exit field"),
        ("Enter", "submit", "Submit"),
    ]
    # SCREENS = {"filters": FilterScreen()}
    tab = reactive("mactive", bindings=True)

    def compose(self) -> ComposeResult:
        with TabbedContent(classes="box", id="tabcont"):
            with TabPane("Active machine", id="mactive", classes="box"):
                with Center():
                    yield Static(
                        f"Welcome, {INFO['user']['name']}!",
                        classes="box label"
                    )
                with Container(id="info-box", classes="box"):
                    yield LabelInfo("Name")
                    yield LabelInfo("IP", "Copy",)
                    yield LabelInfo("OS")
                    yield LabelInfo("Difficulty")
                with Container(id="flags-box", classes="box"):
                    with Container(id="flags-type-box"):
                        yield Static("User")
                        yield ButtonFlag("user")
                        yield Static("Root")
                        yield ButtonFlag("root")
                    yield InputFlag("flag")
                with Container(id="actions-box", classes="box"):
                    yield ButtonAction("stop")
                    yield ButtonAction("reset")
                    yield Select(DATA["vpn_opts"],
                                 value=DATA["vpn_curr"],
                                 id="vpn",
                                 allow_blank=False)
                    yield ButtonAction("download")
            with TabPane("Machine list", id="mlist", classes="box-no-bottom"):
                with Container(id="search-box", classes="box-no-top"):
                    yield Input(placeholder="Search", id="search")
                    yield Button("Filters", id="filters")
                with Container():
                    yield DataTable()
        yield CtrlFooter()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Machine", "OS", "Difficulty", "Tags")

        table.add_rows([[m_name, m_diff, m_os, ", ".join(TAGS["by_machine"][m_name])]
                        if m_status == "retired"
                        else [m_name, m_diff, m_os, ""]
                        for m_name, (_, m_diff, m_os, m_status) in sorted(
                                MACH["by_name"].items(),
                                key=lambda x: x[1][0],
                                reverse=True)])

    def key_ctrl_c(self) -> None:
        self.app.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "filters":
            # self.push_screen("filters")
            self.push_screen(FilterScreen())
        elif event.button.id in ["cancel", "accept"]:
            # self.pop_screen("filters")
            self.pop_screen()

    def check_action(self, action: str, _) -> bool:
        if (isinstance(self.app.focused, InputFlag)
            or isinstance(self.app.focused, Input)):
            if action in ["escape", "submit"]:
                return True
        else:
            if self.tab == "mactive":
                if action in ["escape", "submit", "active", "filters"]:
                    return False
                return True
            else:
                if action in ["escape", "submit", "machines", "stop", "reset"]:
                    return False
                return True
        return False

    def action_flag(self) -> None:
        self.query_one("#flag").focus()

    def action_search(self) -> None:
        self.query_one("#search").focus()

    def action_filters(self) -> None:
        # self.push_screen("filters")
        self.push_screen(FilterScreen())

    def action_machines(self) -> None:
        self.query_one("#tabcont").active = "mlist"
        self.tab = "mlist"
        self.set_focus(self.query_one(ContentTabs))

    def action_active(self) -> None:
        self.query_one("#tabcont").active = "mactive"
        self.tab = "mactive"
        self.set_focus(self.query_one(ContentTabs))

    def action_show_tab(self, tab: str) -> None:
        self.query_one("#tabcont").active = tab
        self.tab = tab

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self.tab = event.tabbed_content.active

    def key_escape(self) -> None:
        if isinstance(self.app.screen, FilterScreen):
            self.pop_screen()
        else:
            self.set_focus(self.query_one(ContentTabs))



if __name__ == "__main__":
    try:
        TOKEN = os.environ["HTB_KEY"]
    except KeyError:
        pass
    try:
        if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "1"):
            with open('.api') as f:
                TOKEN = f.read().strip()
        else:
            with open('.api2') as f:
                TOKEN = f.read().strip()
    except FileNotFoundError:
        pass
    if not TOKEN:
        print("Error, HTB_KEY not set or .api file missing")
        sys.exit(1)
    headers = httpx.Headers({
        "Authorization": f"Bearer {TOKEN}",
        "Host": "labs.hackthebox.com",
        "Origin": "https://app.hackthebox.com",
        "Referer": "https://app.hackthebox.com",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; "
                       "rv:128.0) Gecko/20100101 Firefox/128.0"),
    })
    cl = httpx.Client(headers=headers)

    load_cache()
    load_cache("mach")
    load_cache("tags")
    if not INFO:
        print("Updating user data...")
        retrieve_user_info()
        retrieve_current_machine()
        if active_machine():
            retrieve_info_machine()
        retrieve_vpn_servers()
        retrieve_current_vpn()
        # save_cache()
    if not MACH:
        print("Updating machines data...")
        MACH = {
            "by_name": {},
            "by_difficulty": defaultdict(list),
            "by_os": defaultdict(list),
            "by_status": {"free": [], "retired": []}
        }
        retrieve_machines(retired=True)
        retrieve_machines()
        # save_cache("mach")
    if not TAGS:
        print("Updating tags data...")
        TAGS = {"by_machine": {}}
        retrieve_tags()
        # save_cache("tags")

    prepare_gui_data()

    app = HTBPanel()
    app.run()
