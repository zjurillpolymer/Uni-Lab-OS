"""OS 本地模式与 Backend 对齐的试剂（Reagent）公共接口测试。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from unilabos.app.scheduler.inventory.backend_api import install_backend_resource_api
from unilabos.app.scheduler.inventory.backend_contract import BackendResourceService
from unilabos.app.scheduler.inventory.schemas import InventoryLedgerEntryResponse
from unilabos.app.scheduler.inventory.store import SCHEMA_VERSION, InventoryStore


def _client(tmp_path) -> tuple[TestClient, InventoryStore]:
    """创建绑定隔离 ``inventory.db`` 的公共合同客户端。"""

    store = InventoryStore(str(tmp_path / "inventory.db"))
    app = FastAPI()
    install_backend_resource_api(app, BackendResourceService(store))
    return TestClient(app), store


def _container_template(client: TestClient) -> str:
    """同步带 ``container`` 标签的试剂瓶模板并返回稳定 UUID。"""

    template = client.post(
        "/api/v1/resource-templates",
        json={
            "resources": [
                {
                    "id": "local.reagent_bottle",
                    "display_name": "本地试剂瓶",
                    "registry_type": "material",
                    "category": ["container"],
                    "metadata": {"capacity": {"max_volume_ul": 1000000}},
                    "model": {},
                    "class": {},
                    "handles": [],
                    "config_info": [],
                    "scene": [],
                    "device_params": {},
                }
            ]
        },
    ).json()["data"]["templates"][0]
    return template["uuid"]


def _container(client: TestClient) -> str:
    """创建一个不携带内容物的旧式空容器。"""

    template_uuid = _container_template(client)
    response = client.post(
        "/api/v1/materials",
        json={
            "resource_template_uuid": template_uuid,
            "name": "乙醇瓶",
            "barcode": "LOCAL-ETHANOL-001",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["uuid"]


def test_material_create_can_atomically_include_reagent(tmp_path) -> None:
    """公共物料创建接口可在同一事务内创建容器和试剂内容。"""

    client, store = _client(tmp_path)
    template_uuid = _container_template(client)
    info_uuid = _reagent_info(client)

    created = client.post(
        "/api/v1/materials",
        json={
            "resource_template_uuid": template_uuid,
            "name": "内联乙醇瓶",
            "barcode": "LOCAL-INLINE-ETHANOL-001",
            "reagent": {
                "reagent_info_uuid": info_uuid,
                "quantity": 500,
                "quantity_unit": "mL",
                "concentration_value": 95,
                "concentration_unit": "%",
                "source": "frontend:workbench",
                "meta_data": {"batch": "A-001"},
            },
        },
    )

    assert created.status_code == 201
    assert created.json()["code"] == 0
    result = created.json()["data"]
    assert result["reagent"]["material_uuid"] == result["uuid"]
    assert result["reagent"]["reagent_info_uuid"] == info_uuid
    assert result["reagent"]["quantity"] == 500
    assert result["reagent_info"]["uuid"] == info_uuid
    assert store.query_one(
        "SELECT COUNT(*) AS count FROM material WHERE barcode=?",
        ("LOCAL-INLINE-ETHANOL-001",),
    ) == {"count": 1}
    assert store.query_one(
        "SELECT COUNT(*) AS count FROM reagent WHERE material_uuid=?",
        (result["uuid"],),
    ) == {"count": 1}
    assert store.query_one(
        "SELECT COUNT(*) AS count FROM inventory_ledger "
        "WHERE material_uuid=? AND subject_type='reagent'",
        (result["uuid"],),
    ) == {"count": 1}
    assert store.query_one(
        "SELECT COUNT(*) AS count FROM sync_outbox "
        "WHERE aggregate_id=? AND aggregate_type='reagent'",
        (result["reagent"]["uuid"],),
    ) == {"count": 1}
    store.close()


def test_invalid_inline_reagent_rolls_back_material(tmp_path) -> None:
    """内联试剂校验失败时不得留下半成品容器。"""

    client, store = _client(tmp_path)
    template_uuid = _container_template(client)

    rejected = client.post(
        "/api/v1/materials",
        json={
            "resource_template_uuid": template_uuid,
            "name": "不应保留的容器",
            "barcode": "LOCAL-INLINE-ROLLBACK-001",
            "reagent": {
                "cas": "67-56-1",
                "quantity": 10,
                "quantity_unit": "mL",
            },
        },
    )

    assert rejected.json()["code"] == 4001
    assert store.query_one(
        "SELECT COUNT(*) AS count FROM material WHERE barcode=?",
        ("LOCAL-INLINE-ROLLBACK-001",),
    ) == {"count": 0}
    assert store.query_one("SELECT COUNT(*) AS count FROM reagent") == {"count": 0}
    assert store.query_one("SELECT COUNT(*) AS count FROM sync_outbox") == {"count": 0}
    store.close()


def _reagent_info(client: TestClient) -> str:
    """登记乙醇身份并返回稳定 UUID。"""

    response = client.post(
        "/api/v1/reagent-infos",
        json={
            "cas": "64-17-5",
            "name": "乙醇",
            "name_en": "Ethanol",
            "aliases": ["酒精"],
            "molecular_formula": "C2H6O",
            "density_g_per_ml": 0.789,
            "physical_state": "liquid",
            "meta_data": {"storage": "阴凉通风"},
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["uuid"]


def test_inventory_database_reuses_edge_ledger_for_reagent_schema(tmp_path) -> None:
    """证明试剂结构复用 Edge 台账与发件箱，不建立第二张物料台账。"""

    store = InventoryStore(str(tmp_path / "inventory.db"))
    tables = {
        row["name"]
        for row in store.query_all(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    assert store.query_one("PRAGMA user_version") == {"user_version": SCHEMA_VERSION}
    assert {
        "reagent_info",
        "reagent",
        "sample",
        "current_substance",
        "inventory_ledger",
        "sync_outbox",
    } <= tables
    assert "material_ledger_entry" not in tables
    ledger_columns = {
        row["name"] for row in store.query_all("PRAGMA table_info(inventory_ledger)")
    }
    assert {
        "entry_uuid",
        "material_uuid",
        "subject_type",
        "quantity_delta",
        "quantity_unit",
        "revision",
        "workflow_task_uuid",
        "workflow_node_job_uuid",
    } <= ledger_columns
    store.close()


def test_v8_development_database_merges_duplicate_ledger_on_reopen(tmp_path) -> None:
    """证明早期 v8 开发库会把重复台账并入统一台账并删除旧表。"""

    database = tmp_path / "inventory.db"
    store = InventoryStore(str(database))
    with store.transaction() as conn:
        conn.execute(
            """CREATE TABLE material_ledger_entry(
            uuid TEXT PRIMARY KEY,material_uuid TEXT,event_type TEXT,
            operator_type TEXT,changes TEXT,extension TEXT,trace_id TEXT,
            recorded_at TEXT,workflow_task_uuid TEXT,workflow_node_job_uuid TEXT,
            subject_type TEXT,subject_uuid TEXT,quantity_delta REAL,
            quantity_unit TEXT,revision INTEGER)"""
        )
        conn.execute(
            """INSERT INTO material_ledger_entry VALUES(
            'old-entry','old-material','adjust','frontend','{"result":{"quantity":4}}',
            '{}','trace-old','2026-08-26T10:00:00.000Z',NULL,NULL,'reagent',
            'old-reagent',-1,'mL',2)"""
        )
    store.close()

    reopened = InventoryStore(str(database))
    migrated = reopened.query_one(
        "SELECT * FROM inventory_ledger WHERE entry_uuid='old-entry'"
    )

    assert migrated is not None
    assert migrated["op_type"] == "reagent.adjust"
    assert migrated["aggregate_id"] == "old-reagent"
    assert migrated["material_uuid"] == "old-material"
    assert migrated["quantity_delta"] == -1
    assert migrated["quantity_unit"] == "mL"
    assert migrated["revision"] == 2
    assert reopened.query_one(
        "SELECT 1 AS found FROM sqlite_master "
        "WHERE type='table' AND name='material_ledger_entry'"
    ) is None
    reopened.close()


def test_reagent_info_crud_and_local_compound_lookup(tmp_path) -> None:
    """证明化学品身份可在 OS 本地模式独立登记、纠错、查询和受限删除。"""

    client, store = _client(tmp_path)
    identity = _reagent_info(client)

    page = client.get("/api/v1/reagent-infos?page=1&page_size=100").json()["data"]
    registered = client.get("/api/v1/compounds/64-17-5").json()["data"]
    unavailable = client.get("/api/v1/compounds/67-56-1").json()["data"]
    updated = client.put(
        f"/api/v1/reagent-infos/{identity}",
        json={
            "name": "无水乙醇",
            "aliases": [],
            "physical_state": "liquid",
            "name_en": None,
            "meta_data": {},
        },
    ).json()["data"]

    assert page["total"] == 1
    assert page["items"][0]["aliases"] == ["酒精"]
    assert registered["status"] == "registered"
    assert unavailable["status"] == "unavailable"
    assert updated["name"] == "无水乙醇"
    assert updated["name_en"] is None
    assert client.delete(f"/api/v1/reagent-infos/{identity}").json() == {"code": 0}
    store.close()


def test_reagent_instance_revision_history_and_delete_guard(tmp_path) -> None:
    """证明容器试剂 CRUD、乐观修订、台账和化学身份删除保护在同一库闭合。"""

    client, store = _client(tmp_path)
    material_uuid = _container(client)
    info_uuid = _reagent_info(client)

    created = client.post(
        "/api/v1/reagents",
        json={
            "material_uuid": material_uuid,
            "cas": "64-17-5",
            "quantity": 500,
            "quantity_unit": "mL",
            "concentration_value": 95,
            "concentration_unit": "%",
            "source": "frontend:workbench",
            "meta_data": {},
        },
    )
    reagent_uuid = created.json()["data"]["uuid"]
    conflict = client.put(
        f"/api/v1/reagents/{reagent_uuid}",
        json={
            "quantity": 450,
            "quantity_unit": "mL",
            "expected_revision": 9,
            "meta_data": {},
        },
    ).json()
    updated = client.put(
        f"/api/v1/reagents/{reagent_uuid}",
        json={
            "quantity": 450,
            "quantity_unit": "mL",
            "expected_revision": 1,
            "concentration_value": 95,
            "concentration_unit": "%",
            "meta_data": {},
        },
    ).json()["data"]
    history = client.get(
        f"/api/v1/materials/{material_uuid}/reagent-history?page=1&page_size=100"
    ).json()["data"]
    history_by_uuid = client.get(
        f"/api/v1/reagent-history/{history['items'][0]['uuid']}"
    ).json()["data"]
    ledger = store.query_all(
        "SELECT * FROM inventory_ledger WHERE subject_type='reagent' "
        "ORDER BY ledger_id"
    )
    outbox = store.query_all(
        "SELECT * FROM sync_outbox WHERE aggregate_type='reagent' "
        "ORDER BY sequence"
    )
    # 扩展统一台账列后，旧 ``/inventory/ledger`` 诊断 DTO 仍必须能序列化整行。
    InventoryLedgerEntryResponse.model_validate(ledger[-1])
    protected = client.delete(f"/api/v1/reagent-infos/{info_uuid}").json()
    protected_container = client.delete(
        f"/api/v1/materials/{material_uuid}"
    ).json()

    assert created.status_code == 201
    assert created.json()["data"]["revision"] == 1
    assert created.json()["data"]["reagent_info"]["uuid"] == info_uuid
    assert conflict["code"] == 4002
    assert updated["revision"] == 2
    assert updated["quantity"] == 450
    assert [entry["event_type"] for entry in history["items"]] == [
        "adjust",
        "add",
    ]
    assert history_by_uuid == history["items"][0]
    assert [entry["op_type"] for entry in ledger] == [
        "reagent.add",
        "reagent.adjust",
    ]
    assert [entry["event_type"] for entry in outbox] == [
        "reagent.add",
        "reagent.adjust",
    ]
    assert [entry["entry_uuid"] for entry in ledger] == [
        entry["event_id"] for entry in outbox
    ]
    assert protected["code"] == 4000
    assert protected_container["code"] == 2005

    assert client.delete(f"/api/v1/reagents/{reagent_uuid}").json() == {"code": 0}
    # 试剂虽已删除，身份仍被历史实例和台账引用，必须保留用于追溯。
    assert client.delete(f"/api/v1/reagent-infos/{info_uuid}").json()["code"] == 4000
    store.close()


def test_reagent_requires_registered_identity_and_container_material(tmp_path) -> None:
    """证明试剂创建不会隐式注册 CAS，也拒绝把非容器物料冒充试剂瓶。"""

    client, store = _client(tmp_path)
    material_uuid = _container(client)

    missing_identity = client.post(
        "/api/v1/reagents",
        json={
            "material_uuid": material_uuid,
            "cas": "67-56-1",
            "quantity": 10,
            "quantity_unit": "mL",
            "meta_data": {},
        },
    ).json()

    assert missing_identity["code"] == 4001
    store.close()
