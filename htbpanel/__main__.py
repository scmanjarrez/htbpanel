import asyncio
import os

import httpx

import htbpanel.htbapi as api
import htbpanel.tui as tui
from htbpanel.database import Database


def headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "htbpanel/0.1 (https://github.com/scmanjarrez/htbpanel)",
    }


async def main():
    client = httpx.AsyncClient(headers=headers(TOKEN), timeout=30)
    db = Database()
    if not db.vpn_count():
        db.vpn_add(await api.query_vpn_servers(client))

    if not db.machine_count():
        db.machine_add(await api.query_boxes(client))

    info = await api.query_user_info(client)
    info.update(await api.query_current_box(client))
    info.update(await api.query_current_vpn(client))


    # missing = db.machines_by_notag()
    # db.add_tags_info(await api.query_tags(client, missing))

    app = tui.HTBPanel(client, db, info)
    await app.run_async()


if __name__ == "__main__":
    TOKEN = os.environ.get("HTB_KEY")
    if TOKEN is None:
        try:
            with open(".api") as f:
                TOKEN = f.read().strip()
        except FileNotFoundError:
            print("Error: HTB_KEY unset or .api file missing")
            exit(1)
    asyncio.run(main())
