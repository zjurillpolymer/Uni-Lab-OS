"""工站入口预留的库存数据库增量结构。"""

from __future__ import annotations

import sqlite3

_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS station_ingress_reservation (
    uuid TEXT PRIMARY KEY NOT NULL,
    create_time DATETIME NOT NULL,
    update_time DATETIME NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    backend_task_uuid TEXT,
    invocation_key TEXT,
    carrier_material_uuid TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('reserved', 'in_transit', 'received', 'expired', 'canceled')
    ),
    expires_at DATETIME NOT NULL,
    transport_started_at DATETIME,
    received_at DATETIME,
    canceled_at DATETIME,
    cancel_reason TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    FOREIGN KEY (carrier_material_uuid) REFERENCES material (uuid)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_station_ingress_state_expiry
    ON station_ingress_reservation (state, expires_at, uuid);
CREATE INDEX IF NOT EXISTS idx_station_ingress_backend_task
    ON station_ingress_reservation (backend_task_uuid, invocation_key);

CREATE TABLE IF NOT EXISTS station_ingress_reservation_site (
    reservation_uuid TEXT PRIMARY KEY NOT NULL,
    site_uuid TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    FOREIGN KEY (reservation_uuid) REFERENCES station_ingress_reservation (uuid)
        ON DELETE RESTRICT,
    FOREIGN KEY (site_uuid) REFERENCES site (uuid) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_station_ingress_active_site
    ON station_ingress_reservation_site (site_uuid) WHERE active = 1;

CREATE TABLE IF NOT EXISTS station_ingress_reservation_resource (
    reservation_uuid TEXT NOT NULL,
    lock_key TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    PRIMARY KEY (reservation_uuid, lock_key),
    FOREIGN KEY (reservation_uuid) REFERENCES station_ingress_reservation (uuid)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_station_ingress_active_resource
    ON station_ingress_reservation_resource (lock_key, reservation_uuid)
    WHERE active = 1;
"""

_BACKFILL_ACTIVE_RESOURCES = r"""
UPDATE station_ingress_reservation_resource
SET active = 0
WHERE active = 1 AND reservation_uuid IN (
    SELECT reservation.uuid
    FROM station_ingress_reservation AS reservation
    LEFT JOIN station_ingress_reservation_site AS selected
      ON selected.reservation_uuid = reservation.uuid AND selected.active = 1
    WHERE reservation.state NOT IN ('reserved', 'in_transit')
       OR selected.reservation_uuid IS NULL
);

INSERT OR IGNORE INTO station_ingress_reservation_resource(
    reservation_uuid, lock_key, active
)
SELECT reservation.uuid,
       'material/' || site.material_uuid || '/site/' || site.uuid || '/exclusive',
       1
FROM station_ingress_reservation AS reservation
JOIN station_ingress_reservation_site AS selected
  ON selected.reservation_uuid = reservation.uuid AND selected.active = 1
JOIN site ON site.uuid = selected.site_uuid AND site.deleted_at IS NULL
WHERE reservation.state IN ('reserved', 'in_transit')
UNION
SELECT reservation.uuid, '/devices/' || site.material_uuid, 1
FROM station_ingress_reservation AS reservation
JOIN station_ingress_reservation_site AS selected
  ON selected.reservation_uuid = reservation.uuid AND selected.active = 1
JOIN site ON site.uuid = selected.site_uuid AND site.deleted_at IS NULL
WHERE reservation.state IN ('reserved', 'in_transit')
UNION
SELECT reservation.uuid,
       'material/' || reservation.carrier_material_uuid || '/exclusive',
       1
FROM station_ingress_reservation AS reservation
JOIN station_ingress_reservation_site AS selected
  ON selected.reservation_uuid = reservation.uuid AND selected.active = 1
WHERE reservation.state IN ('reserved', 'in_transit')
UNION
SELECT reservation.uuid, '/devices/' || reservation.carrier_material_uuid, 1
FROM station_ingress_reservation AS reservation
JOIN station_ingress_reservation_site AS selected
  ON selected.reservation_uuid = reservation.uuid AND selected.active = 1
WHERE reservation.state IN ('reserved', 'in_transit');
"""


def migrate_ingress_schema(connection: sqlite3.Connection) -> None:
    """幂等创建入口预留表。

    参数：``connection`` 是库存权威持有的 SQLite 连接。返回：无。异常：结构
    不兼容或外键约束失败时原样传播，调用方不得在半迁移数据库上继续启动。
    """

    connection.executescript(_SCHEMA)
    # 某些只验证单一旧表迁移的 v6 夹具并不包含完整 ``site`` 表；新建的入口
    # 表此时必为空，无需准备引用 ``site`` 的回填语句。真实旧入口事实一旦存在，
    # 仍执行完整 JOIN 并在缺表/损坏时关闭式失败。
    has_legacy_reservation = connection.execute(
        "SELECT 1 FROM station_ingress_reservation LIMIT 1"
    ).fetchone()
    if has_legacy_reservation is not None:
        connection.executescript(_BACKFILL_ACTIVE_RESOURCES)


__all__ = ["migrate_ingress_schema"]
