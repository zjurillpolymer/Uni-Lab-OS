"""由边缘端（Edge）库存 SQLite 支撑的后端形态资源模块。

它是共享前端接口（Frontend Interface）背后的领域实现。遗留 ``/inventory``
适配器仍是边缘端专用操作面；两个适配器写入同一组规范
``resource_template/material/site`` 行。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from unilabos.app.scheduler.inventory.capacity import (
    CAPACITY_KEY,
    capacity_projection,
    material_capacity,
    normalize_capacity,
    validate_material_config,
)
from unilabos.app.scheduler.inventory.dispatch_admission import (
    InventoryMutationConflict,
    assert_inventory_mutation_unclaimed,
)
from unilabos.app.scheduler.inventory.store import (
    InventoryStore,
    SiteOccupancyConflict,
    clear_site_occupancy,
    set_site_occupancy,
)
from unilabos.resources.site_definition import normalize_available_sites


class BackendContractError(RuntimeError):
    """使用后端（Backend）数值响应合同编码的业务错误。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


INVALID_PARAMETER = 1000
DATABASE_CONFLICT = 2005
REAGENT_INFO_IN_USE = 4000
RESOURCE_NOT_FOUND = 4001
RESOURCE_DATA_CONFLICT = 4002
RESOURCE_TEMPLATE_NOT_FOUND = 5000
TEMPLATE_DEFINITION_INVALID = 5003
TEMPLATE_DATA_CONFLICT = 5004
MATERIAL_NOT_FOUND = 6000
MATERIAL_TEMPLATE_NOT_FOUND = 6001
MATERIAL_TEMPLATE_IMMUTABLE = 6002
MATERIAL_PARENT_NOT_FOUND = 6003
MATERIAL_PARENT_CYCLE = 6004
MATERIAL_SITE_NOT_FOUND = 6006
MATERIAL_SITE_OCCUPIED = 6007
MATERIAL_SITE_TEMPLATE_NOT_ALLOWED = 6008
MATERIAL_SITE_CYCLE = 6009
MATERIAL_IDENTITY_CONFLICT = 6010
MATERIAL_ACTIVE_CLAIM_CONFLICT = 6011


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return fallback


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _optional(value: Any) -> Any:
    return None if value in (None, "") else value


def _optional_uuid(value: Any) -> Optional[str]:
    """把未传、空串和全零 UUID 统一解释为未设置。

    参数：``value`` 是已通过 HTTP DTO 校验的可空 UUID。返回：规范
    UUID 字符串或 ``None``。异常：无；非空值交由调用方校验引用。
    """

    identity = str(value or "")
    if identity in ("", "00000000-0000-0000-0000-000000000000"):
        return None
    return identity


class BackendResourceService:
    """提供资源模板（ResourceTemplate）、物料（Material）与库位（Site）权威写入。"""

    def __init__(
        self,
        store: InventoryStore,
        *,
        edge_id: str = "edge-default",
        lab_id: str = "edge-lab",
        monitor: Any = None,
    ):
        """绑定 OS Local 库与当前 Edge 身份。

        参数：``store`` 是唯一库存数据库；``edge_id`` 与 ``lab_id`` 用于同一
        HTTP 合同下需要写入事务发件箱的领域事件。返回：初始化后的资源服务。
        """

        self.store = store
        self.edge_id = edge_id
        self.lab_id = lab_id
        self._monitor = monitor

    def _notify_material_changed(self, material_uuid: str, operation: str) -> None:
        """在 Backend 物料写事务提交后通知本地调度器。"""

        if self._monitor is None:
            return
        try:
            self._monitor.emit(
                "material",
                "material_changed",
                {
                    "material_uuid": str(material_uuid),
                    "operation": operation,
                    "edge_id": self.edge_id,
                    "lab_id": self.lab_id,
                },
            )
        except Exception:
            # 通知故障不能回滚已经成功提交的物料事务。
            pass

    # Resource Template -------------------------------------------------

    def sync_resource_templates(
        self, resources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """同步一代活动资源模板并返回稳定身份回执。

        参数说明：``resources`` 是同批设备与物料资源模板（ResourceTemplate）
        定义。返回：每个注册表（Registry）业务 ID 对应的活动 UUID；已有活动名
        复用 UUID，只有软删除历史时创建新 UUID。异常：空定义、重复业务 ID 或
        SQLite 约束冲突转换为 ``BackendContractError``，整个事务回滚。
        """

        if not resources:
            raise BackendContractError(
                TEMPLATE_DEFINITION_INVALID, "resources is required"
            )
        # ``normalized_names`` 是本批注册表（Registry）业务 ID 的规范唯一集合。
        normalized_names = [
            str(resource.get("id") or "").strip() for resource in resources
        ]
        if any(not name for name in normalized_names) or len(
            set(normalized_names)
        ) != len(normalized_names):
            raise BackendContractError(
                TEMPLATE_DEFINITION_INVALID,
                "resource names are required and must be unique",
            )
        runtime_catalog = self.store.runtime_device_template_catalog
        runtime_catalog_required = (
            self.store.runtime_device_template_catalog_required
        )
        runtime_device_names = self.store.runtime_device_template_names
        # 安装运行时目录后，当前领域包中已有设备仍按原同步接口幂等返回身份，
        # 但不写 SQLite；未知设备或用 resource 类型覆盖设备名会关闭式失败。
        runtime_identity_by_name: dict[str, str] = {}
        for resource, name in zip(resources, normalized_names):
            registry_type = str(
                resource.get("registry_type") or "resource"
            ).strip().lower()
            if name in runtime_device_names and registry_type != "device":
                raise BackendContractError(
                    TEMPLATE_DATA_CONFLICT,
                    "resource template name is owned by the runtime device catalog",
                )
            if registry_type == "device" and runtime_catalog is None:
                if runtime_catalog_required:
                    raise BackendContractError(
                        TEMPLATE_DATA_CONFLICT,
                        "runtime device template catalog is not ready",
                    )
                continue
            if runtime_catalog is not None:
                runtime_uuid = runtime_catalog.resolve_uuid(name)
                if registry_type == "device":
                    if not runtime_uuid:
                        raise BackendContractError(
                            TEMPLATE_DATA_CONFLICT,
                            "device templates are owned by the runtime package catalog",
                        )
                    runtime_identity_by_name[name] = runtime_uuid
                elif runtime_uuid:
                    raise BackendContractError(
                        TEMPLATE_DATA_CONFLICT,
                        "resource template name conflicts with a runtime device",
                    )
        # ``identities`` 只记录本次事务最终采用的活动资源模板稳定身份。
        identities: List[Dict[str, str]] = []
        try:
            with self.store.transaction() as conn:
                for resource, name in zip(resources, normalized_names):
                    runtime_uuid = runtime_identity_by_name.get(name)
                    if runtime_uuid is not None:
                        identities.append({"uuid": runtime_uuid, "name": name})
                        continue
                    # ``existing`` 只能是当前活动业务 ID；软删除历史不得被复活。
                    existing = conn.execute(
                        "SELECT uuid,meta_data,resource_type FROM resource_template "
                        "WHERE name = ? AND deleted_at IS NULL",
                        (name,),
                    ).fetchone()
                    if (
                        runtime_catalog_required
                        and existing is not None
                        and str(existing["resource_type"]) == "device"
                    ):
                        raise BackendContractError(
                            TEMPLATE_DATA_CONFLICT,
                            "persisted device templates are read-only during runtime catalog startup",
                        )
                    template_uuid = str(existing["uuid"]) if existing else str(uuid4())
                    existing_meta = _json(existing["meta_data"], {}) if existing else {}
                    source_uri = resource.get("source_uri")
                    if source_uri is not None and (
                        not isinstance(source_uri, str)
                        or not source_uri.startswith("package://")
                    ):
                        raise BackendContractError(
                            TEMPLATE_DEFINITION_INVALID,
                            "resource template source_uri must use package://",
                        )
                    meta_data = dict(existing_meta)
                    metadata = resource.get("metadata") or {}
                    if not isinstance(metadata, dict):
                        raise BackendContractError(TEMPLATE_DEFINITION_INVALID, "metadata 须为 JSON 对象")
                    if CAPACITY_KEY in metadata:
                        meta_data[CAPACITY_KEY] = normalize_capacity(metadata[CAPACITY_KEY])
                    if source_uri:
                        meta_data["unilab"] = {
                            **_json(meta_data.get("unilab"), {}),
                            "source_uri": source_uri,
                        }
                    # ``class_definition`` 是当前模板冻结的 Python 实现身份合同。
                    class_definition = resource.get("class") or {}
                    # ``schema`` 是资源模板初始化参数的数据/配置命名空间合同。
                    schema = resource.get("init_param_schema") or {}
                    try:
                        # 本地 Backend 也在写边界关闭式校验，避免发布阶段才发现
                        # Registry 库位（Site）模板定义不可被云端实例化。
                        available_sites = normalize_available_sites(
                            resource.get("available_sites")
                        )
                    except ValueError as error:
                        raise BackendContractError(
                            TEMPLATE_DEFINITION_INVALID,
                            f"invalid resource template available_sites: {error}",
                        ) from error
                    # ``data_schema`` 与 ``config_schema`` 分别持久化初始化状态字段合同。
                    data_schema = (schema.get("data") or {}).get("properties") or {}
                    config_schema = (schema.get("config") or {}).get("properties") or {}
                    # ``values`` 是一次 upsert 使用的完整后端（Backend）形态模板行。
                    values = (
                        template_uuid,
                        _now(),
                        _now(),
                        resource.get("description"),
                        _dump(meta_data),
                        name,
                        str(resource.get("display_name") or name),
                        str(resource.get("registry_type") or "resource"),
                        _optional(resource.get("icon")),
                        _dump(resource.get("model") or {}),
                        _optional(class_definition.get("module")),
                        _optional(class_definition.get("type")),
                        _dump(resource.get("category") or []),
                        _dump(data_schema),
                        _dump(config_schema),
                        _dump({}),
                        _dump(resource.get("config_info") or []),
                        _dump(available_sites),
                        _optional(resource.get("cover")),
                        _dump(resource.get("scene") or []),
                        _dump(resource.get("device_params") or {}),
                        _dump({}),
                    )
                    conn.execute(
                        """
                        INSERT INTO resource_template(
                            uuid, create_time, update_time, description, meta_data,
                            name, display_name, resource_type, icon, model, module,
                            language, tags, data_schema, config_schema, pose,
                            config_info, available_sites, cover, scene,
                            device_params, ui_overlay
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(uuid) DO UPDATE SET
                            update_time=excluded.update_time,
                            deleted_at=NULL,
                            description=excluded.description,
                            meta_data=excluded.meta_data,
                            display_name=excluded.display_name,
                            resource_type=excluded.resource_type,
                            icon=excluded.icon,
                            model=excluded.model,
                            module=excluded.module,
                            language=excluded.language,
                            tags=excluded.tags,
                            data_schema=excluded.data_schema,
                            config_schema=excluded.config_schema,
                            config_info=excluded.config_info,
                            available_sites=excluded.available_sites,
                            cover=excluded.cover,
                            scene=excluded.scene,
                            device_params=excluded.device_params
                        """,
                        values,
                    )
                    conn.execute(
                        """
                        INSERT INTO resource_template_inventory(
                            resource_template_uuid, aggregate_version
                        ) VALUES (?,1)
                        ON CONFLICT(resource_template_uuid) DO UPDATE SET
                            aggregate_version=aggregate_version+1
                        """,
                        (template_uuid,),
                    )
                    if "handles" in resource:
                        self._reconcile_resource_handles(
                            conn,
                            template_uuid,
                            resource.get("handles") or [],
                        )
                    identities.append({"uuid": template_uuid, "name": name})
        except sqlite3.IntegrityError as exc:
            raise BackendContractError(
                TEMPLATE_DATA_CONFLICT, "template data conflicts with existing data"
            ) from exc
        return {"templates": identities}

    def list_resource_templates(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str,
        resource_type: str,
    ) -> Dict[str, Any]:
        page = 1 if page <= 0 else page
        page_size = 20 if page_size <= 0 else min(page_size, 100)
        where = ["deleted_at IS NULL", "resource_type <> ?"]
        values: List[Any] = ["framework"]
        if keyword:
            where.append("(LOWER(name) LIKE ? OR LOWER(display_name) LIKE ?)")
            keyword_pattern = f"%{keyword.strip().lower()}%"
            values.extend((keyword_pattern, keyword_pattern))
        if resource_type:
            where.append("resource_type = ?")
            values.append(resource_type.strip())
        offset = (page - 1) * page_size
        rows = self.store.query_all(
            "SELECT uuid,create_time,name,display_name,resource_type,icon,tags "
            f"FROM resource_template WHERE {' AND '.join(where)} "
            "ORDER BY create_time DESC,uuid DESC",
            tuple(values),
        )
        entries = [
            (
                str(row["create_time"]),
                str(row["uuid"]),
                {
                    "uuid": row["uuid"],
                    "name": row["name"],
                    "display_name": row["display_name"],
                    "resource_type": row["resource_type"],
                    "tags": _json(row["tags"], []),
                    **({"icon": row["icon"]} if row["icon"] is not None else {}),
                },
            )
            for row in rows
        ]
        runtime_catalog = self.store.runtime_device_template_catalog
        if runtime_catalog is not None and resource_type.strip() in {"", "device"}:
            normalized_keyword = keyword.strip().lower()
            for detail in runtime_catalog.list():
                if normalized_keyword and normalized_keyword not in str(
                    detail["name"]
                ).lower() and normalized_keyword not in str(
                    detail["display_name"]
                ).lower():
                    continue
                entries.append(
                    (
                        str(detail["create_time"]),
                        str(detail["uuid"]),
                        self._resource_template_summary_from_detail(
                            detail,
                            include_tags=True,
                        ),
                    )
                )
        entries.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        items = [entry[2] for entry in entries]
        page_items = items[offset : offset + page_size]
        return {
            "items": page_items,
            "has_more": len(items) > offset + page_size,
            "page": page,
            "page_size": page_size,
        }

    def get_resource_template(self, template_uuid: str) -> Dict[str, Any]:
        runtime_catalog = self.store.runtime_device_template_catalog
        if runtime_catalog is not None:
            runtime_detail = runtime_catalog.get(template_uuid)
            if runtime_detail is not None:
                return runtime_detail
        row = self.store.query_one(
            "SELECT * FROM resource_template WHERE uuid=? AND deleted_at IS NULL",
            (template_uuid,),
        )
        if row is None:
            raise BackendContractError(
                RESOURCE_TEMPLATE_NOT_FOUND, "Resource template not found"
            )
        result = self._resource_template_row(row)
        result["handles"] = [
            self._resource_handle_row(handle)
            for handle in self.store.query_all(
                "SELECT * FROM resource_handle_template "
                "WHERE resource_template_uuid=? AND deleted_at IS NULL "
                "ORDER BY io_type,name,uuid",
                (template_uuid,),
            )
        ]
        return result

    def delete_resource_template(self, template_uuid: str) -> None:
        runtime_catalog = self.store.runtime_device_template_catalog
        if runtime_catalog is not None and runtime_catalog.contains_uuid(template_uuid):
            raise BackendContractError(
                TEMPLATE_DATA_CONFLICT,
                "runtime device templates can only be changed by the domain package",
            )
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT uuid,name,resource_type FROM resource_template "
                "WHERE uuid=? AND deleted_at IS NULL",
                (template_uuid,),
            ).fetchone()
            if row is None:
                raise BackendContractError(
                    RESOURCE_TEMPLATE_NOT_FOUND, "Resource template not found"
                )
            if self.store.runtime_device_template_catalog_required and (
                str(row["resource_type"]) == "device"
                or str(row["name"]) in self.store.runtime_device_template_names
            ):
                raise BackendContractError(
                    TEMPLATE_DATA_CONFLICT,
                    "runtime device templates can only be changed by the domain package",
                )
            in_use = conn.execute(
                "SELECT 1 FROM material WHERE resource_template_uuid=? "
                "AND deleted_at IS NULL LIMIT 1",
                (template_uuid,),
            ).fetchone()
            if in_use:
                raise BackendContractError(
                    TEMPLATE_DATA_CONFLICT, "Resource template is in use"
                )
            conn.execute(
                "UPDATE resource_template SET deleted_at=?,update_time=? WHERE uuid=?",
                (_now(), _now(), template_uuid),
            )
            conn.execute(
                "UPDATE resource_handle_template SET deleted_at=?,update_time=? "
                "WHERE resource_template_uuid=? AND deleted_at IS NULL",
                (_now(), _now(), template_uuid),
            )

    # Material ----------------------------------------------------------

    def create_material(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """创建物料或设备实例，并从对应模板权威校验模板身份。

        参数：``values`` 保持既有 Backend 物料写入合同。返回：新实例详情。
        设备模板从当前进程内目录解析，物料模板从 SQLite 解析；两者均继续使用
        同一个 ``resource_template_uuid`` 外部字段。
        """

        material_uuid = str(uuid4())
        template_uuid = str(values.get("resource_template_uuid") or "")
        parent_uuid = _optional(values.get("parent_uuid"))
        barcode = str(values.get("barcode") or "")
        name = str(values.get("name") or "").strip()
        inline_reagent = values.get("reagent")
        content_snapshot: Optional[Dict[str, Dict[str, Any]]] = None
        if not template_uuid or not name:
            raise BackendContractError(
                INVALID_PARAMETER, "resource_template_uuid and name are required"
            )
        runtime_catalog = self.store.runtime_device_template_catalog
        runtime_template = (
            runtime_catalog.get(template_uuid) if runtime_catalog is not None else None
        )
        try:
            with self.store.transaction() as conn:
                template = runtime_template or conn.execute(
                    "SELECT resource_type FROM resource_template "
                    "WHERE uuid=? AND deleted_at IS NULL",
                    (template_uuid,),
                ).fetchone()
                if template is None:
                    raise BackendContractError(
                        MATERIAL_TEMPLATE_NOT_FOUND,
                        "Resource template associated with the material not found",
                    )
                if parent_uuid:
                    self._require_material(conn, parent_uuid, MATERIAL_PARENT_NOT_FOUND)
                placement = values.get("site_placement")
                target_site_uuid = _optional_uuid(
                    (placement or {}).get("site_uuid")
                )
                if parent_uuid or placement:
                    assert_inventory_mutation_unclaimed(
                        conn,
                        material_uuids=(parent_uuid,) if parent_uuid else (),
                        site_uuids=(target_site_uuid,) if target_site_uuid else (),
                    )
                now = _now()
                conn.execute(
                    """
                    INSERT INTO material(
                        uuid,create_time,update_time,deleted_at,description,meta_data,
                        resource_template_uuid,parent_uuid,class,type,barcode,name,config,data
                    ) VALUES (?,?,?,NULL,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        material_uuid,
                        now,
                        now,
                        values.get("description"),
                        _dump(values.get("meta_data") or {}),
                        template_uuid,
                        parent_uuid,
                        str(template["resource_type"]),
                        str(template["resource_type"]),
                        barcode,
                        name,
                        _dump(values.get("config") or {}),
                        _dump({}),
                    ),
                )
                conn.execute(
                    "INSERT INTO material_inventory(material_uuid,legacy_template_id) "
                    "VALUES (?,?)",
                    (material_uuid, template_uuid),
                )
                if inline_reagent is None:
                    validate_material_config(conn, material_uuid, values.get("config") or {})
                if values.get("relative_position") is not None:
                    self._upsert_relative_position(
                        conn, material_uuid, values["relative_position"]
                    )
                if placement:
                    self._apply_site_placement(
                        conn, material_uuid, template_uuid, placement
                    )
                if inline_reagent is not None:
                    # 物料与内容物必须共享当前事务；不能先提交空容器，再调用独立
                    # ``POST /reagents``，否则中途失败会留下半成品。
                    from unilabos.app.scheduler.inventory.reagent_contract import (
                        BackendReagentService,
                    )

                    reagent_values = dict(inline_reagent)
                    reagent_values["material_uuid"] = material_uuid
                    content_snapshot = BackendReagentService(
                        self.store,
                        edge_id=self.edge_id,
                        lab_id=self.lab_id,
                    ).create_reagent_in_transaction(conn, reagent_values)
        except InventoryMutationConflict as error:
            raise BackendContractError(
                MATERIAL_ACTIVE_CLAIM_CONFLICT,
                str(error),
            ) from error
        except BackendContractError:
            raise
        except sqlite3.IntegrityError as exc:
            raise BackendContractError(
                MATERIAL_IDENTITY_CONFLICT,
                "Material barcode or sibling name conflicts with an existing material",
            ) from exc
        self._notify_material_changed(material_uuid, "created")
        result = self.get_material(material_uuid)
        result["children"] = []
        if content_snapshot is not None:
            result.update(content_snapshot)
        return result

    def list_materials(
        self,
        *,
        page: int,
        page_size: int,
        name: str,
        barcode: str,
        resource_template_uuid: Optional[str],
    ) -> Dict[str, Any]:
        page = max(page, 1)
        page_size = 20 if page_size <= 0 else min(page_size, 100)
        where = ["deleted_at IS NULL"]
        values: List[Any] = []
        if name:
            where.append("name LIKE ?")
            values.append(f"%{name}%")
        if barcode:
            where.append("barcode = ?")
            values.append(barcode)
        if resource_template_uuid:
            where.append("resource_template_uuid = ?")
            values.append(resource_template_uuid)
        predicate = " AND ".join(where)
        total = self.store.query_one(
            f"SELECT COUNT(*) AS count FROM material WHERE {predicate}", tuple(values)
        )
        rows = self.store.query_all(
            "SELECT material.*,(SELECT meta_data FROM resource_template "
            "WHERE uuid=material.resource_template_uuid AND deleted_at IS NULL) "
            f"AS capacity_template_meta FROM material WHERE {predicate} "
            "ORDER BY create_time DESC,uuid DESC LIMIT ? OFFSET ?",
            (*values, page_size, (page - 1) * page_size),
        )
        return {
            "items": [self._material_row(row) for row in rows],
            "total": int(total["count"] if total else 0),
            "page": page,
            "page_size": page_size,
        }

    def get_material(self, material_uuid: str) -> Dict[str, Any]:
        """读取物料当前详情、修订、相对位置与库位关系。

        参数：``material_uuid`` 是物料稳定身份。返回：面向 Backend
        公共合同的完整物料投影。异常：物料不存在时抛 ``6000``。
        """

        row = self.store.query_one(
            "SELECT material.*,material_inventory.aggregate_version,"
            "(SELECT meta_data FROM resource_template WHERE uuid=material.resource_template_uuid "
            "AND deleted_at IS NULL) AS capacity_template_meta "
            "FROM material JOIN material_inventory "
            "ON material_inventory.material_uuid=material.uuid "
            "WHERE material.uuid=? AND material.deleted_at IS NULL",
            (material_uuid,),
        )
        if row is None:
            raise BackendContractError(MATERIAL_NOT_FOUND, "Material not found")
        result = self._material_row(dict(row))
        position = self.store.query_one(
            "SELECT * FROM relative_position "
            "WHERE material_uuid=? AND deleted_at IS NULL",
            (material_uuid,),
        )
        result["relative_position"] = (
            self._relative_position_row(dict(position)) if position else None
        )
        result["sites"] = self.list_sites(material_uuid)
        current_site = self.store.query_one(
            "SELECT * FROM site WHERE occupied_material_uuid=? AND deleted_at IS NULL",
            (material_uuid,),
        )
        result["current_site"] = self._site_row(current_site) if current_site else None
        return result

    def update_material(
        self, material_uuid: str, values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 Backend 公共合同原子更新物料及其库位占用。

        参数：``material_uuid`` 是物料稳定身份，``values`` 包含三态更新字段、可选
        期望修订。返回：提交后的完整物料详情。异常：物料、父级、库位、修订或
        唯一约束冲突时抛
        ``BackendContractError``；事务失败不保留部分更新。
        """

        try:
            with self.store.transaction() as conn:
                current = self._require_material(conn, material_uuid)
                specified_marker = values.get("_specified_fields")
                specified = (
                    set(specified_marker)
                    if specified_marker is not None
                    else {key for key in values if not key.startswith("_")}
                )
                placement = values.get("site_placement")
                parent_is_mutated = (
                    "parent_uuid" in specified
                    and values.get("parent_uuid") is not None
                    and _optional_uuid(values.get("parent_uuid"))
                    != _optional_uuid(current["parent_uuid"])
                )
                if placement or parent_is_mutated:
                    target_site_uuid = _optional_uuid(
                        (placement or {}).get("site_uuid")
                    )
                    assert_inventory_mutation_unclaimed(
                        conn,
                        material_uuids=tuple(
                            item
                            for item in (
                                material_uuid,
                                _optional_uuid(current["parent_uuid"]),
                                _optional_uuid(values.get("parent_uuid")),
                            )
                            if item
                        ),
                        site_uuids=(target_site_uuid,) if target_site_uuid else (),
                    )
                template_uuid = str(current["resource_template_uuid"])
                template_value = values.get("resource_template_uuid")
                if (
                    "resource_template_uuid" in specified
                    and template_value is not None
                    and str(template_value) != template_uuid
                ):
                    raise BackendContractError(
                        MATERIAL_TEMPLATE_IMMUTABLE,
                        "Resource template of an existing material cannot be changed",
                    )
                inventory = conn.execute(
                    "SELECT aggregate_version FROM material_inventory "
                    "WHERE material_uuid=?",
                    (material_uuid,),
                ).fetchone()
                expected_revision = values.get("expected_revision")
                if (
                    expected_revision is not None
                    and int(expected_revision) != int(inventory["aggregate_version"])
                ):
                    raise BackendContractError(
                        RESOURCE_DATA_CONFLICT,
                        "Material revision has changed",
                    )
                parent_uuid = (
                    _optional_uuid(values.get("parent_uuid"))
                    if "parent_uuid" in specified
                    and values.get("parent_uuid") is not None
                    else _optional_uuid(current["parent_uuid"])
                )
                if parent_uuid:
                    self._require_material(conn, parent_uuid, MATERIAL_PARENT_NOT_FOUND)
                    self._check_parent_cycle(conn, material_uuid, parent_uuid)
                barcode = (
                    str(values.get("barcode") or "")
                    if "barcode" in specified and values.get("barcode") is not None
                    else str(current["barcode"] or "")
                )
                name = (
                    str(values.get("name") or "").strip()
                    if "name" in specified and values.get("name") is not None
                    else str(current["name"] or "")
                )
                description = (
                    values.get("description")
                    if "description" in specified
                    and values.get("description") is not None
                    else current["description"]
                )
                meta_data = (
                    values.get("meta_data")
                    if "meta_data" in specified
                    and values.get("meta_data") is not None
                    else _json(current["meta_data"], {})
                )
                config = (
                    values.get("config")
                    if "config" in specified
                    and values.get("config") is not None
                    else _json(current["config"], {})
                )
                # 旧客户端整体提交 config 时，不应无意清除新版本维护的上限。
                previous_config = _json(current["config"], {})
                capacity_specified = (
                    "config" in specified and isinstance(values.get("config"), dict)
                    and CAPACITY_KEY in values["config"]
                )
                if capacity_specified:
                    config = {**previous_config, **config,
                              CAPACITY_KEY: normalize_capacity(config[CAPACITY_KEY])}
                for key in (CAPACITY_KEY, "max_volume"):
                    if key in previous_config and key not in config:
                        config = {**config, key: previous_config[key]}
                previous_capacity = material_capacity(conn, material_uuid)["capacity"]
                if config != previous_config or capacity_specified:
                    assert_inventory_mutation_unclaimed(conn, material_uuids=(material_uuid,))
                    validate_material_config(conn, material_uuid, config,
                                             replace_loading_limits=capacity_specified,
                                             validate_stock=(capacity_specified or
                                                             config.get("max_volume") != previous_config.get("max_volume")))
                conn.execute(
                    """
                    UPDATE material SET parent_uuid=?,barcode=?,name=?,description=?,
                        meta_data=?,config=?,update_time=?
                    WHERE uuid=? AND deleted_at IS NULL
                    """,
                    (
                        parent_uuid,
                        barcode,
                        name,
                        description,
                        _dump(meta_data),
                        _dump(config),
                        _now(),
                        material_uuid,
                    ),
                )
                if config != previous_config or capacity_specified:
                    from unilabos.app.scheduler.inventory.reagent_contract import BackendReagentService

                    BackendReagentService(self.store, edge_id=self.edge_id, lab_id=self.lab_id).record_material_capacity_change(
                        conn, material_uuid, previous_capacity, replace_loading_limits=capacity_specified,
                        configuration_changed=(normalize_capacity(previous_config.get(CAPACITY_KEY))
                                               != normalize_capacity(config.get(CAPACITY_KEY))),
                    )
                if values.get("_relative_position_specified"):
                    if values.get("relative_position") is None:
                        conn.execute(
                            "UPDATE relative_position SET deleted_at=?,update_time=? "
                            "WHERE material_uuid=? AND deleted_at IS NULL",
                            (_now(), _now(), material_uuid),
                        )
                    else:
                        self._upsert_relative_position(
                            conn, material_uuid, values["relative_position"]
                        )
                if placement:
                    self._apply_site_placement(
                        conn, material_uuid, template_uuid, placement
                    )
                conn.execute(
                    "UPDATE material_inventory SET aggregate_version=aggregate_version+1 "
                    "WHERE material_uuid=?",
                    (material_uuid,),
                )
        except InventoryMutationConflict as error:
            raise BackendContractError(
                MATERIAL_ACTIVE_CLAIM_CONFLICT,
                str(error),
            ) from error
        except BackendContractError:
            raise
        except sqlite3.IntegrityError as exc:
            raise BackendContractError(
                MATERIAL_IDENTITY_CONFLICT,
                "Material barcode or sibling name conflicts with an existing material",
            ) from exc
        self._notify_material_changed(material_uuid, "updated")
        return self.get_material(material_uuid)

    def delete_material(self, material_uuid: str) -> None:
        try:
            with self.store.transaction() as conn:
                self._require_material(conn, material_uuid)
                assert_inventory_mutation_unclaimed(
                    conn,
                    material_uuids=(material_uuid,),
                )
                linked = conn.execute(
                """
                SELECT 1 FROM material
                WHERE parent_uuid=? AND deleted_at IS NULL
                UNION ALL
                SELECT 1 FROM site
                WHERE deleted_at IS NULL
                  AND (material_uuid=? OR occupied_material_uuid=?)
                UNION ALL
                SELECT 1 FROM reagent
                WHERE material_uuid=? AND deleted_at IS NULL
                UNION ALL
                SELECT 1 FROM sample
                WHERE material_uuid=? AND deleted_at IS NULL
                UNION ALL
                SELECT 1 FROM current_substance
                WHERE material_uuid=? AND deleted_at IS NULL
                LIMIT 1
                """,
                (
                    material_uuid,
                    material_uuid,
                    material_uuid,
                    material_uuid,
                    material_uuid,
                    material_uuid,
                ),
            ).fetchone()
                if linked:
                    raise BackendContractError(
                        DATABASE_CONFLICT,
                        "Material is referenced by a child, Site, or container content",
                    )
                now = _now()
                conn.execute(
                    "UPDATE relative_position SET deleted_at=?,update_time=? "
                    "WHERE material_uuid=? AND deleted_at IS NULL",
                    (now, now, material_uuid),
                )
                conn.execute(
                    "UPDATE material SET deleted_at=?,update_time=? WHERE uuid=?",
                    (now, now, material_uuid),
                )
                conn.execute(
                    "UPDATE material_inventory SET aggregate_version=aggregate_version+1 "
                    "WHERE material_uuid=?",
                    (material_uuid,),
                )
        except InventoryMutationConflict as error:
            raise BackendContractError(
                MATERIAL_ACTIVE_CLAIM_CONFLICT,
                str(error),
            ) from error
        self._notify_material_changed(material_uuid, "deleted")

    def material_graph(self) -> Dict[str, Any]:
        materials = self.store.query_all(
            "SELECT material.*,material_inventory.aggregate_version,"
            "resource_template.resource_type AS template_resource_type,"
            "resource_template.meta_data AS capacity_template_meta "
            "FROM material "
            "JOIN material_inventory ON material_inventory.material_uuid=material.uuid "
            "LEFT JOIN resource_template ON resource_template.uuid=material.resource_template_uuid "
            "WHERE material.deleted_at IS NULL ORDER BY material.create_time,material.uuid"
        )
        return {
            "nodes": [
                {
                    "material": self._material_graph_row(material),
                    "relative_position": self._relative_position_for_material(
                        material["uuid"]
                    ),
                    "sites": self.list_sites(material["uuid"]),
                    "current_site_uuid": self._current_site_uuid(material["uuid"]),
                    "handles": self._resource_template_handles(
                        material["resource_template_uuid"]
                    ),
                    "resource_template": self._resource_template_summary(
                        material["resource_template_uuid"]
                    ),
                }
                for material in materials
            ]
        }

    # Site and state ----------------------------------------------------

    def list_sites(self, material_uuid: str) -> List[Dict[str, Any]]:
        rows = self.store.query_all(
            "SELECT * FROM site WHERE material_uuid=? AND deleted_at IS NULL "
            "ORDER BY sort_order,create_time,uuid",
            (material_uuid,),
        )
        return [self._site_row(row) for row in rows]

    def get_site(self, site_uuid: str) -> Dict[str, Any]:
        row = self.store.query_one(
            "SELECT * FROM site WHERE uuid=? AND deleted_at IS NULL", (site_uuid,)
        )
        if row is None:
            raise BackendContractError(
                MATERIAL_SITE_NOT_FOUND, "Material site not found"
            )
        return self._site_row(row)

    def append_material_state(
        self, material_uuid: str, values: Dict[str, Any]
    ) -> Dict[str, Any]:
        state_data = values.get("state_data")
        if not isinstance(state_data, dict) or not state_data:
            raise BackendContractError(INVALID_PARAMETER, "state_data is required")
        state_uuid = str(uuid4())
        observed_at = values.get("observed_at") or _now()
        now = _now()
        with self.store.transaction() as conn:
            self._require_material(conn, material_uuid)
            conn.execute(
                """
                INSERT INTO material_state_history(
                    uuid,create_time,update_time,deleted_at,description,meta_data,
                    material_uuid,status,state_data,source,observed_at
                ) VALUES (?,?,?,NULL,?,?,?,?,?,?,?)
                """,
                (
                    state_uuid,
                    now,
                    now,
                    values.get("description"),
                    _dump(values.get("meta_data") or {}),
                    material_uuid,
                    _optional(values.get("status")),
                    _dump(state_data),
                    _optional(values.get("source")),
                    observed_at,
                ),
            )
            conn.execute(
                "UPDATE material SET data=?,update_time=? WHERE uuid=?",
                (_dump(state_data), now, material_uuid),
            )
            conn.execute(
                "UPDATE material_inventory SET aggregate_version=aggregate_version+1 "
                "WHERE material_uuid=?",
                (material_uuid,),
            )
        return self.get_material_state(state_uuid)

    def get_material_state(self, state_uuid: str) -> Dict[str, Any]:
        row = self.store.query_one(
            "SELECT * FROM material_state_history WHERE uuid=? AND deleted_at IS NULL",
            (state_uuid,),
        )
        if row is None:
            raise BackendContractError(MATERIAL_NOT_FOUND, "Material state not found")
        return self._state_row(row)

    def list_material_states(
        self,
        material_uuid: str,
        *,
        before_time: Optional[str],
        before_uuid: Optional[str],
        limit: int,
    ) -> Dict[str, Any]:
        self.get_material(material_uuid)
        limit = 20 if limit <= 0 else min(limit, 100)
        where = ["material_uuid=?", "deleted_at IS NULL"]
        values: List[Any] = [material_uuid]
        if before_time and before_uuid:
            where.append("(observed_at < ? OR (observed_at = ? AND uuid < ?))")
            values.extend((before_time, before_time, before_uuid))
        rows = self.store.query_all(
            "SELECT * FROM material_state_history "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY observed_at DESC,uuid DESC LIMIT ?",
            (*values, limit),
        )
        items = [self._state_row(row) for row in rows]
        return {
            "items": items,
            "next_before_time": items[-1]["observed_at"] if items else None,
            "next_before_uuid": items[-1]["uuid"] if items else None,
        }

    def latest_material_state(self, material_uuid: str) -> Dict[str, Any]:
        self.get_material(material_uuid)
        row = self.store.query_one(
            "SELECT * FROM material_state_history WHERE material_uuid=? "
            "AND deleted_at IS NULL ORDER BY observed_at DESC,uuid DESC LIMIT 1",
            (material_uuid,),
        )
        if row is None:
            raise BackendContractError(MATERIAL_NOT_FOUND, "Material state not found")
        return self._state_row(row)

    # Internal invariants ----------------------------------------------

    @staticmethod
    def _reconcile_resource_handles(
        conn: sqlite3.Connection,
        template_uuid: str,
        handles: List[Dict[str, Any]],
    ) -> None:
        seen: set[tuple[str, str]] = set()
        retained: List[str] = []
        for handle in handles:
            name = str(handle.get("handler_key") or "").strip()
            io_type = str(handle.get("io_type") or "").strip()
            handle_type = str(handle.get("data_type") or "").strip()
            if (
                not name
                or not handle_type
                or io_type not in {"source", "target", "bidirectional"}
            ):
                raise BackendContractError(
                    TEMPLATE_DEFINITION_INVALID,
                    "resource handle requires handler_key, data_type, and valid io_type",
                )
            business_key = (io_type, name)
            if business_key in seen:
                raise BackendContractError(
                    TEMPLATE_DEFINITION_INVALID,
                    f"duplicate {io_type} resource handle {name}",
                )
            seen.add(business_key)
            existing = conn.execute(
                "SELECT uuid FROM resource_handle_template "
                "WHERE resource_template_uuid=? AND io_type=? AND name=?",
                (template_uuid, io_type, name),
            ).fetchone()
            handle_uuid = str(existing["uuid"]) if existing else str(uuid4())
            now = _now()
            conn.execute(
                """
                INSERT INTO resource_handle_template(
                    uuid,create_time,update_time,deleted_at,description,meta_data,
                    resource_template_uuid,name,display_name,type,io_type,
                    source,key,side
                ) VALUES (?,?,?,NULL,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(uuid) DO UPDATE SET
                    update_time=excluded.update_time,
                    deleted_at=NULL,
                    description=excluded.description,
                    meta_data=excluded.meta_data,
                    display_name=excluded.display_name,
                    type=excluded.type,
                    source=excluded.source,
                    key=excluded.key,
                    side=excluded.side
                """,
                (
                    handle_uuid,
                    now,
                    now,
                    _optional(handle.get("description")),
                    _dump({}),
                    template_uuid,
                    name,
                    str(handle.get("label") or name),
                    handle_type,
                    io_type,
                    _optional(handle.get("data_source")),
                    _optional(handle.get("data_key")),
                    _optional(handle.get("side")),
                ),
            )
            retained.append(handle_uuid)
        if retained:
            markers = ",".join("?" for _ in retained)
            conn.execute(
                "UPDATE resource_handle_template SET deleted_at=?,update_time=? "
                "WHERE resource_template_uuid=? AND deleted_at IS NULL "
                f"AND uuid NOT IN ({markers})",
                (_now(), _now(), template_uuid, *retained),
            )
        else:
            conn.execute(
                "UPDATE resource_handle_template SET deleted_at=?,update_time=? "
                "WHERE resource_template_uuid=? AND deleted_at IS NULL",
                (_now(), _now(), template_uuid),
            )

    @staticmethod
    def _require_material(
        conn: sqlite3.Connection, material_uuid: str, code: int = MATERIAL_NOT_FOUND
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM material WHERE uuid=? AND deleted_at IS NULL",
            (material_uuid,),
        ).fetchone()
        if row is None:
            raise BackendContractError(code, "Material not found")
        return row

    @staticmethod
    def _upsert_relative_position(
        conn: sqlite3.Connection,
        material_uuid: str,
        position: Dict[str, Any],
    ) -> None:
        existing = conn.execute(
            "SELECT uuid,create_time FROM relative_position WHERE material_uuid=?",
            (material_uuid,),
        ).fetchone()
        position_uuid = str(existing["uuid"]) if existing else str(uuid4())
        create_time = str(existing["create_time"]) if existing else _now()
        now = _now()
        conn.execute(
            """
            INSERT INTO relative_position(
                uuid,create_time,update_time,deleted_at,description,meta_data,
                material_uuid,position_x,position_y,position_z,depth,length,width,
                scale_x,scale_y,scale_z,rotation_x,rotation_y,rotation_z
            ) VALUES (?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(uuid) DO UPDATE SET
                update_time=excluded.update_time,
                deleted_at=NULL,
                description=excluded.description,
                meta_data=excluded.meta_data,
                position_x=excluded.position_x,
                position_y=excluded.position_y,
                position_z=excluded.position_z,
                depth=excluded.depth,
                length=excluded.length,
                width=excluded.width,
                scale_x=excluded.scale_x,
                scale_y=excluded.scale_y,
                scale_z=excluded.scale_z,
                rotation_x=excluded.rotation_x,
                rotation_y=excluded.rotation_y,
                rotation_z=excluded.rotation_z
            """,
            (
                position_uuid,
                create_time,
                now,
                position.get("description"),
                _dump(position.get("meta_data") or {}),
                material_uuid,
                float(position.get("position_x") or 0),
                float(position.get("position_y") or 0),
                float(position.get("position_z") or 0),
                float(position.get("depth") or 0),
                float(position.get("length") or 0),
                float(position.get("width") or 0),
                float(position.get("scale_x", 1)),
                float(position.get("scale_y", 1)),
                float(position.get("scale_z", 1)),
                float(position.get("rotation_x") or 0),
                float(position.get("rotation_y") or 0),
                float(position.get("rotation_z") or 0),
            ),
        )

    def _relative_position_for_material(
        self, material_uuid: str
    ) -> Optional[Dict[str, Any]]:
        row = self.store.query_one(
            "SELECT * FROM relative_position "
            "WHERE material_uuid=? AND deleted_at IS NULL",
            (material_uuid,),
        )
        return self._relative_position_row(row) if row else None

    @staticmethod
    def _check_parent_cycle(
        conn: sqlite3.Connection, material_uuid: str, parent_uuid: str
    ) -> None:
        cursor: Optional[str] = parent_uuid
        seen = {material_uuid}
        while cursor:
            if cursor in seen:
                raise BackendContractError(
                    MATERIAL_PARENT_CYCLE,
                    "Material parent relationship creates a cycle",
                )
            seen.add(cursor)
            row = conn.execute(
                "SELECT parent_uuid FROM material WHERE uuid=? AND deleted_at IS NULL",
                (cursor,),
            ).fetchone()
            cursor = row["parent_uuid"] if row else None

    def _apply_site_placement(
        self,
        conn: sqlite3.Connection,
        material_uuid: str,
        template_uuid: str,
        placement: Dict[str, Any],
    ) -> None:
        """在当前物料写事务中校验并修改精确库位占用。

        参数：``conn`` 是库存事务；其余参数给出物料、模板和 place/remove 命令。
        返回：无；成功时 place 同步父物料并占用目标库位，remove 仅解除精确库位。
        异常：库位不存在、已占用、模板不允许或形成父级环时抛合同错误。
        """

        action = str(placement.get("action") or "")
        site_uuid = _optional_uuid(placement.get("site_uuid"))
        if action == "remove":
            if site_uuid is not None:
                raise BackendContractError(
                    INVALID_PARAMETER, "remove must not provide site_uuid"
                )
            clear_site_occupancy(
                conn,
                material_uuid=material_uuid,
                update_time=_now(),
            )
            return
        if action != "place" or not site_uuid:
            raise BackendContractError(
                INVALID_PARAMETER, "site_placement action must be place or remove"
            )
        site = conn.execute(
            "SELECT * FROM site WHERE uuid=? AND deleted_at IS NULL", (site_uuid,)
        ).fetchone()
        if site is None:
            raise BackendContractError(
                MATERIAL_SITE_NOT_FOUND, "Material site not found"
            )
        if site["material_uuid"] == material_uuid:
            raise BackendContractError(
                MATERIAL_SITE_CYCLE, "Material cannot occupy its own Site"
            )
        allowed = _json(site["allowed_resource_template_uuids"], [])
        if allowed and template_uuid not in allowed:
            raise BackendContractError(
                MATERIAL_SITE_TEMPLATE_NOT_ALLOWED,
                "Material resource template is not allowed by the target site",
            )
        occupied = _optional(site["occupied_material_uuid"])
        if occupied and occupied != material_uuid:
            raise BackendContractError(
                MATERIAL_SITE_OCCUPIED, "Target site is occupied by another material"
            )
        owner_material_uuid = str(site["material_uuid"])
        self._check_parent_cycle(conn, material_uuid, owner_material_uuid)
        timestamp = _now()
        try:
            set_site_occupancy(
                conn,
                site_uuid=site_uuid,
                material_uuid=material_uuid,
                update_time=timestamp,
            )
        except SiteOccupancyConflict as error:
            code = (
                MATERIAL_SITE_CYCLE
                if error.code == "site_occupancy_cycle"
                else MATERIAL_SITE_OCCUPIED
            )
            raise BackendContractError(code, str(error)) from error
        conn.execute(
            "UPDATE material SET parent_uuid=?,update_time=? "
            "WHERE uuid=? AND deleted_at IS NULL",
            (owner_material_uuid, timestamp, material_uuid),
        )

    def _current_site_uuid(self, material_uuid: str) -> Optional[str]:
        row = self.store.query_one(
            "SELECT uuid FROM site WHERE occupied_material_uuid=? "
            "AND deleted_at IS NULL",
            (material_uuid,),
        )
        return str(row["uuid"]) if row else None

    @staticmethod
    def _base_row(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "uuid": row["uuid"],
            "create_time": row["create_time"],
            "update_time": row["update_time"],
            "description": row.get("description"),
            "meta_data": _json(row.get("meta_data"), {}),
        }

    @classmethod
    def _resource_template_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """把持久行投影为后端形态资源模板（ResourceTemplate）DTO。

        参数：``cls`` 是投影方法所属服务类，``row`` 是 SQLite 查询得到的资源模板
        行。返回：JSON 字段已解码且 ``available_sites`` 缺省为空数组的独立字典；
        本方法不创建实例库位（Site）。
        """

        result = cls._base_row(row)
        for field in (
            "name",
            "display_name",
            "resource_type",
            "header",
            "footer",
            "icon",
            "module",
            "language",
            "cover",
            "manufacturer_uuid",
        ):
            result[field] = row.get(field)
        for field, fallback in (
            ("model", {}),
            ("tags", []),
            ("data_schema", {}),
            ("config_schema", {}),
            ("pose", {}),
            ("config_info", []),
            ("available_sites", []),
            ("scene", []),
            ("device_params", {}),
            ("ui_overlay", {}),
        ):
            result[field] = _json(row.get(field), fallback)
        return result

    @classmethod
    def _resource_handle_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        result = cls._base_row(row)
        result.update(
            {
                "resource_template_uuid": row["resource_template_uuid"],
                "name": row["name"],
                "display_name": row["display_name"],
                "type": row["type"],
                "io_type": row["io_type"],
            }
        )
        for field in ("source", "key", "side"):
            if row.get(field) is not None:
                result[field] = row[field]
        return result

    @classmethod
    def _material_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """把 SQLite 物料行投影为 Backend 公共物料 DTO。

        参数：``row`` 是物料行，可选携带聚合修订。返回：JSON
        字段已解码的物料字典；存在修订时同步返回 ``revision``。
        异常：缺少必需行字段时保留原生映射异常。
        """

        result = cls._base_row(row)
        result.update(
            {
                "resource_template_uuid": row["resource_template_uuid"],
                "parent_uuid": row.get("parent_uuid"),
                "class": row["class"],
                "barcode": row["barcode"],
                "name": row["name"],
                "config": _json(row.get("config"), {}),
                "data": _json(row.get("data"), {}),
            }
        )
        if "aggregate_version" in row:
            result["revision"] = int(row["aggregate_version"])
        result.update(capacity_projection(
            row.get("config"), row.get("data"), row.get("capacity_template_meta")
        ))
        return result

    @classmethod
    def _material_graph_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """Project the authoritative Backend-shaped Material used by graph reads."""

        result = cls._material_row(row)
        result["type"] = str(row.get("type") or row.get("template_resource_type") or "")
        result["revision"] = int(row["aggregate_version"])
        return result

    def _resource_template_summary(self, template_uuid: str) -> Dict[str, Any]:
        runtime_catalog = self.store.runtime_device_template_catalog
        if runtime_catalog is not None:
            detail = runtime_catalog.get(template_uuid)
            if detail is not None:
                return self._resource_template_summary_from_detail(detail)
        row = self.store.query_one(
            "SELECT uuid,name,display_name,resource_type,icon FROM resource_template "
            "WHERE uuid=? AND deleted_at IS NULL",
            (template_uuid,),
        )
        if row is None:
            raise BackendContractError(RESOURCE_TEMPLATE_NOT_FOUND, "Resource template not found")
        result = {
            "uuid": row["uuid"],
            "name": row["name"],
            "display_name": row["display_name"],
            "resource_type": row["resource_type"],
        }
        if row.get("icon") is not None:
            result["icon"] = row["icon"]
        return result

    @staticmethod
    def _resource_template_summary_from_detail(
        detail: Dict[str, Any],
        *,
        include_tags: bool = False,
    ) -> Dict[str, Any]:
        """从内存设备模板详情构造原有列表或物料图摘要。"""

        result = {
            "uuid": detail["uuid"],
            "name": detail["name"],
            "display_name": detail["display_name"],
            "resource_type": detail["resource_type"],
        }
        if include_tags:
            result["tags"] = list(detail.get("tags") or [])
        if detail.get("icon") is not None:
            result["icon"] = detail["icon"]
        return result

    def _resource_template_handles(self, template_uuid: str) -> List[Dict[str, Any]]:
        """从内存设备目录或 SQLite 物料模板读取资源 Handle。"""

        runtime_catalog = self.store.runtime_device_template_catalog
        if runtime_catalog is not None:
            detail = runtime_catalog.get(template_uuid)
            if detail is not None:
                return list(detail.get("handles") or [])
        return [
            self._resource_handle_row(handle)
            for handle in self.store.query_all(
                "SELECT * FROM resource_handle_template "
                "WHERE resource_template_uuid=? AND deleted_at IS NULL "
                "ORDER BY io_type,name,uuid",
                (template_uuid,),
            )
        ]

    @classmethod
    def _site_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        result = cls._base_row(row)
        result.update(
            {
                "material_uuid": row["material_uuid"],
                "name": row["name"],
                "sort_order": int(row["sort_order"]),
                "allowed_resource_template_uuids": _json(
                    row.get("allowed_resource_template_uuids"), []
                ),
                "occupied_material_uuid": row.get("occupied_material_uuid"),
                "position_x": float(row["position_x"]),
                "position_y": float(row["position_y"]),
                "position_z": float(row["position_z"]),
                "depth": float(row["depth"]),
                "length": float(row["length"]),
                "width": float(row["width"]),
            }
        )
        return result

    @classmethod
    def _relative_position_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        result = cls._base_row(row)
        result["material_uuid"] = row["material_uuid"]
        for field in (
            "position_x",
            "position_y",
            "position_z",
            "depth",
            "length",
            "width",
            "scale_x",
            "scale_y",
            "scale_z",
            "rotation_x",
            "rotation_y",
            "rotation_z",
        ):
            result[field] = float(row[field])
        return result

    @classmethod
    def _state_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        result = cls._base_row(row)
        result.update(
            {
                "material_uuid": row["material_uuid"],
                "status": row.get("status"),
                "state_data": _json(row.get("state_data"), {}),
                "source": row.get("source"),
                "observed_at": row["observed_at"],
            }
        )
        return result


__all__ = ["BackendContractError", "BackendResourceService"]
