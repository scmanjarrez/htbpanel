import asyncio

from tqdm import tqdm, trange

API = "https://labs.hackthebox.com/api/v4"
SLEEP = 2.5


async def query_user_info(client):
    res = await client.get(f"{API}/user/info")
    data = res.json()["info"]
    return {
        "user": {
            "name": data["name"],
            "id": data["id"],
            "vip": data["canAccessVIP"],
        }
    }


# Only VIP/VIP+ machines return IP
async def query_current_box(client):
    res = await client.get(f"{API}/machine/active")
    data = res.json()["info"]
    out = {"current_box": None}
    if data is not None:
        info = await query_box_info(client, data["name"])
        out["current_box"] = {
            "name": data["name"],
            "id": info["id"],
            "difficulty": info["difficultyText"],
            "os": info["os"],
            "user_own": info["authUserInUserOwns"],
            "root_own": info["authUserInRootOwns"],
            "ip": info["ip"],
        }
    return out


async def query_box_info(client, name):
    res = await client.get(f"{API}/machine/profile/{name}")
    return res.json()["info"]


async def query_vpn_servers(client):
    res = await client.get(
        f"{API}/connections/servers", params={"product": "release_arena"}
    )
    return res.json()["data"]


async def query_current_vpn(client):
    data_all = await query_vpn_servers(client)
    res = await client.get(f"{API}/connection/status")
    data = res.json()
    out = {
        "current_vpn": {
            "name": data_all["assigned"]["friendly_name"],
            "id": data_all["assigned"]["id"],
        }
    }
    if data:
        out["current_vpn"]["address"] = f"{data[0]['server']['hostname']}:1337"
        out["current_vpn"]["ip"] = data[0]["connection"]["ip4"]
    return out


async def query_boxes(client):
    data = {"active": [], "retired": []}
    data["active"].extend(await query_active_boxes(client))
    data["retired"].extend(await query_retired_boxes(client))
    return data


async def query_active_boxes(client):
    res = await client.get(f"{API}/machine/paginated", params={"per_page": 100})
    data = res.json()
    return data["data"]


async def query_retired_boxes(client):
    total = []
    res = await client.get(
        f"{API}/machine/list/retired/paginated", params={"per_page": 100}
    )
    data = res.json()
    total.extend(data["data"])
    for page in trange(
        2, data["meta"]["last_page"] + 1, desc="Querying retired boxes"
    ):
        res = await client.get(
            f"{API}/machine/list/retired/paginated",
            params={"per_page": 100, "page": page},
        )
        data = res.json()
        total.extend(data["data"])
        await asyncio.sleep(SLEEP)
    return total


async def query_retired_free_boxes(client):
    res = await client.get(
        f"{API}/machine/list/retired/paginated",
        params={"per_page": 100, "free": 1},
    )
    data = res.json()
    return data["data"]


async def query_new_boxes(client, db):
    active_res = await query_active_boxes(client)
    data = {"active": active_res}
    parsed_active = db._machine_parse(data, "active")
    server_active = {d for d, *_ in parsed_active}
    local_active = set(db.machines_by_active())
    new = server_active - local_active
    if new:
        db.machine_add(data)
        free_res = await query_retired_free_boxes(client)
        data["retired"] = free_res
        parsed_free = db._machine_parse(data, "retired")
        server_retired = {d for d, *_ in parsed_free}
        db.machines_reset_free_active()
        db.machines_update_active(server_active)
        db.machines_update_free(server_retired)


async def query_tags(client, missing):
    total_tags = []
    total_relations = []
    for m_id in tqdm(missing, desc="Querying box tags"):
        res = await client.get(f"{API}/machine/tags/{m_id}")
        data = res.json()["info"]
        for tag in data:
            total_tags.append((tag["id"], tag["category"], tag["name"]))
            total_relations.append((m_id, tag["id"]))
        await asyncio.sleep(SLEEP)
    return total_tags, total_relations


async def machine_action(client, action, machine_id):
    match action:
        case "start":
            res = await client.post(
                f"{API}/vm/spawn", json={"machine_id": machine_id}
            )
        case "stop":
            res = await client.post(
                f"{API}/vm/terminate", json={"machine_id": machine_id}
            )
        case "reset":
            res = await client.post(
                f"{API}/vm/reset", json={"machine_id": machine_id}
            )
    out = res.json()
    if isinstance(out["success"], str):
        out["success"] = bool(int(out["success"]))
    return out


async def submit_flag(client, machine_id, flag):
    res = await client.post(
        f"{API}/machine/own", json={"id": machine_id, "flag": flag}
    )
    return res.json()


# async def switch_vpn(client, vpn):
#     res = await client.post(f"{API}/connections/servers/switch/{vpn}")
#     if res.status_code == 200:
#         ovpn = await client.get(f"{API}/access/ovpnfile/{vpn}/0")
#         if ovpn.status_code == 200:
#             with open(f"lab_{INFO['user']['name']}.ovpn", "w") as f:
#                 f.write(ovpn.text)
