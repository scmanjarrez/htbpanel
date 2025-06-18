import sqlite3

DB = "htb.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB)
        self.cursor = self.conn.cursor()
        self.setup()

    def setup(self):
        self.cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS vpns (
                id INTEGER PRIMARY KEY,
                name TEXT
            );

            CREATE TABLE IF NOT EXISTS machines (
                id INTEGER PRIMARY KEY,
                name TEXT,
                difficulty TEXT,
                os TEXT,
                free INTEGER,
                active INTEGER,
                user_own INTEGER,
                root_own INTEGER
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                category TEXT,
                name TEXT
            );

            CREATE TABLE IF NOT EXISTS machine_tag (
                machine_id INTEGER,
                tag_id INTEGER,
                FOREIGN KEY (machine_id) REFERENCES machines(id),
                FOREIGN KEY (tag_id) REFERENCES tags(id),
                PRIMARY KEY (machine_id, tag_id)
            );
            """
        )

    def _int2ico(self, value1, value2=None):
        if value2 is not None:
            return f"{self._int2ico(value1)}/{self._int2ico(value2)}"
        return "✓" if value1 else "x"

    def machines_with_tags(self):
        self.cursor.execute(
            "SELECT machines.name, machines.difficulty, "
            "machines.os, machines.free, machines.user_own, machines.root_own, "
            "GROUP_CONCAT(tags.name, ',') AS tags "
            "FROM machines "
            "LEFT JOIN machine_tag ON machines.id = machine_tag.machine_id "
            "LEFT JOIN tags ON machine_tag.tag_id = tags.id "
            "GROUP BY machines.id, machines.name "
            "ORDER BY machines.free DESC, machines.name"
        )
        return [
            (n, d, o, self._int2ico(f), self._int2ico(u, r), t)
            for (n, d, o, f, u, r, t) in self.cursor.fetchall()
        ]

    def machine_count(self):
        self.cursor.execute("SELECT COUNT(*) FROM machines")
        return self.cursor.fetchone()[0]

    def _machine_parse(self, data, machine_type):
        return [
            (
                machine["id"],
                machine["name"],
                machine["difficultyText"],
                machine["os"],
                int(machine["free"]),
                int(machine_type == "active"),
                int(machine["authUserInUserOwns"]),
                int(machine["authUserInRootOwns"]),
            )
            for machine in data[machine_type]
        ]

    def machine_add(self, data):
        insert = self._machine_parse(data, "active")
        if "retired" in data:
            insert.extend(self._machine_parse(data, "retired"))
        self.cursor.executemany(
            "INSERT OR IGNORE INTO machines "
            "(id, name, difficulty, os, free, active, user_own, root_own) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            insert,
        )
        self.conn.commit()

    def machine_own(self, id, own_type):
        self.cursor.execute(
            f"UPDATE machines SET {own_type}_own = 1 WHERE id = ?",
            [id],
        )
        self.conn.commit()

    def machine_by_id(self, id):
        self.cursor.execute("SELECT name FROM machines WHERE id = ?", [id])
        return self.cursor.fetchone()[0]

    def machines_reset_free_active(self):
        self.cursor.execute("UPDATE machines SET free = 0, active = 0 ")
        self.conn.commit()

    def machines_update_active(self, ids):
        self.cursor.execute(
            f"UPDATE machines SET free = 1, active = 1 "
            f"WHERE id IN ({','.join('?' for _ in ids)})",
            list(ids),
        )
        self.conn.commit()

    def machines_update_free(self, ids):
        self.cursor.execute(
            f"UPDATE machines SET free = 1 "
            f"WHERE id IN ({','.join('?' for _ in ids)})",
            list(ids),
        )
        self.conn.commit()

    def machines_os_list(self):
        self.cursor.execute(
            "SELECT os FROM machines GROUP BY os",
        )
        return [(d, idx) for idx, (d,) in enumerate(self.cursor.fetchall())]

    def machines_by_active(self):
        self.cursor.execute(
            "SELECT id FROM machines WHERE active = 1",
        )
        return [d for (d,) in self.cursor.fetchall()]

    def machines_by_vip(self, vip):
        if vip:
            self.cursor.execute("SELECT name, id FROM machines ORDER BY name")
        else:
            self.cursor.execute(
                "SELECT name, id FROM machines WHERE free = 1 ORDER BY name",
            )
        return self.cursor.fetchall()

    def machines_by_filters(self, filters):
        condition = ""
        params = []
        tags = []
        tags_params = []
        for a in ["category", "area", "vulnerability"]:
            for _v in filters[a]:
                tags.append("?")
                tags_params.append(_v)
        first = False
        for k, v in filters.items():
            if k == "status":
                if v == "Complete":
                    condition += (
                        "WHERE machines.user_own = 1 AND machines.root_own = 1 "
                    )
                elif v == "Incomplete":
                    condition += "WHERE (machines.user_own = 0 OR machines.root_own = 0) "
                else:
                    first = True
            elif v and k in ["os", "difficulty"]:
                condition += "WHERE " if first else "AND "
                first = False
                condition += f"machines.{k} IN ({','.join(['?' for _ in v])}) "
                params.extend([_v for _v in v])
            elif v and k == "availability":
                condition += "WHERE " if first else "AND "
                first = False
                for _v in v:
                    condition += f"machines.{_v.lower()} = 1 "
        if tags:
            condition += f"{'WHERE' if first else 'AND'} tags.name IN ({','.join(tags)}) "
            params.extend(tags_params)
        self.cursor.execute(
            f"SELECT machines.name, machines.difficulty, "
            f"machines.os, machines.free, machines.user_own, machines.root_own, "
            f"GROUP_CONCAT(tags.name, ',') AS tags "
            f"FROM machines "
            f"LEFT JOIN machine_tag ON machines.id = machine_tag.machine_id "
            f"LEFT JOIN tags ON machine_tag.tag_id = tags.id "
            f"{condition}"
            f"GROUP BY machines.id, machines.name "
            f"ORDER BY machines.free DESC, machines.name",
            params,
        )
        return [
            (n, d, o, self._int2ico(f), self._int2ico(u, r), t)
            for (n, d, o, f, u, r, t) in self.cursor.fetchall()
        ]

    def machines_by_notag(self):
        self.cursor.execute(
            "SELECT machines.id "
            "FROM machines "
            "LEFT JOIN machine_tag "
            "ON machines.id = machine_tag.machine_id "
            "WHERE machines.active = 0 "
            "AND machine_tag.tag_id IS NULL"
        )
        return [mach for (mach,) in self.cursor.fetchall()]

    def machines_by_name(self, name):
        self.cursor.execute(
            "SELECT machines.name, machines.difficulty, "
            "machines.os, machines.free, machines.user_own, machines.root_own, "
            "GROUP_CONCAT(tags.name, ',') AS tags "
            "FROM machines "
            "LEFT JOIN machine_tag ON machines.id = machine_tag.machine_id "
            "LEFT JOIN tags ON machine_tag.tag_id = tags.id "
            "WHERE machines.name LIKE ?"
            "GROUP BY machines.id, machines.name "
            "ORDER BY machines.free DESC, machines.name",
            [f"%{name}%"],
        )
        return [
            (n, d, o, self._int2ico(f), self._int2ico(u, r), t)
            for (n, d, o, f, u, r, t) in self.cursor.fetchall()
        ]

    def vpn_list(self):
        self.cursor.execute("SELECT name, id FROM vpns")
        return self.cursor.fetchall()

    def vpn_count(self):
        self.cursor.execute("SELECT COUNT(*) FROM vpns")
        return self.cursor.fetchone()[0]

    def vpn_add(self, data):
        insert = [
            (server["id"], server["friendly_name"])
            for region in data["options"].values()
            for info in region.values()
            for server in info["servers"].values()
        ]
        self.cursor.executemany(
            "INSERT OR IGNORE INTO vpns (id, name) VALUES (?, ?)",
            insert,
        )
        self.conn.commit()

    def tag_add(self, data):
        self.cursor.executemany(
            "INSERT OR IGNORE INTO tags (id, category, name) VALUES (?, ?, ?)",
            data,
        )
        self.conn.commit()

    def machine_tag_add(self, data):
        self.cursor.executemany(
            "INSERT OR IGNORE INTO machine_tag "
            "(machine_id, tag_id) "
            "VALUES (?, ?)",
            data,
        )
        self.conn.commit()

    def tag_bulk_add(self, data):
        tags, relations = data
        self.tag_add(tags)
        self.machine_tag_add(relations)

    def tags_category_list(self):
        self.cursor.execute(
            "SELECT name, id "
            "FROM tags "
            "WHERE category = 'Category' "
            "ORDER BY name"
        )
        return self.cursor.fetchall()

    def tags_area_list(self):
        self.cursor.execute(
            "SELECT name, id "
            "FROM tags "
            "WHERE category = 'Area of Interest' "
            "ORDER BY name"
        )
        return self.cursor.fetchall()

    def tags_vulnerability_list(self):
        self.cursor.execute(
            "SELECT name, id "
            "FROM tags "
            "WHERE category = 'Vulnerabilities' "
            "ORDER BY name"
        )
        return self.cursor.fetchall()
