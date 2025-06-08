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
    if data is not None:
        return await query_box_info(client, data["name"])
    else:
        return {"current_box": None}


async def query_box_info(client, name):
    res = await client.get(f"{API}/machine/profile/{name}")
    data = res.json()["info"]
    return {
        "current_box": {
            "name": name,
            "id": data["id"],
            "difficulty": data["difficultyText"],
            "os": data["os"],
            "user_own": data["authUserInUserOwns"],
            "root_own": data["authUserInRootOwns"],
            "ip": data["ip"],
        }
    }


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


# async def switch_vpn(vpn: int) -> None:
#     res = CLIENT.post(f"{API}/connections/servers/switch/{vpn}")
#     if res.status_code == 200:
#         ovpn = CLIENT.get(f"{API}/access/ovpnfile/{vpn}/0")
#         if ovpn.status_code == 200:
#             with open(f"lab_{INFO['user']['name']}.ovpn", "w") as f:
#                 f.write(ovpn.text)


# def machine_action(machine: int, action: str) -> bool:
#     if action == "spawn":
#         res = CLIENT.post(f"{API}/machine/play/{machine}")
#     elif action == "stop":
#         res = CLIENT.post(f"{API}/machine/stop")
#     else:
#         res = CLIENT.post(f"{API}/vm/reset", json={"machine_id": machine})
#     return res.status_code == 200


# def submit_flag(flag: str) -> bool:
#     res = CLIENT.post(
#         f"{API}/machine/own", json={"id": INFO["mach"]["id"], "flag": flag}
#     )
#     return res.status_code == 200
