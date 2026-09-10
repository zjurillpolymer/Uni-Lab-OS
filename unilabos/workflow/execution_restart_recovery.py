"""设备执行进程重启后的工作流任务（WorkflowTask）失败收敛。"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from unilabos.workflow.event_writer import (
    append_frontend_event,
    append_runtime_event,
)
from unilabos.workflow.job_evidence import record_job_result
from unilabos.workflow.json_codec import decode_json_bytes, encode_json
from unilabos.workflow.manual_confirmation import close_pending_manual_confirmation
from unilabos.workflow.execution_lock_lease import release_execution_locks
from unilabos.workflow.physical_settlement_policy import (
    PhysicalSettlementPolicyError,
    TerminalSettlementPlan,
    plan_terminal_settlement,
)
from unilabos.workflow.station_status_projection import (
    append_job_state_event,
    append_task_state_event,
)
from unilabos.workflow.resource_lock_plan import failed_explicit_resource_interval_ids
from unilabos.workflow.store import StoreConflict, StoreNotFound, utc_now

EXECUTION_PROCESS_RESTARTED = "execution_process_restarted"
TASK_ABORTED_BY_RUNTIME_RESTART = "task_aborted_by_runtime_restart"
_IN_FLIGHT_JOB_STATES = frozenset({"dispatched", "running", "cancel_requested"})
_TERMINAL_JOB_STATES = frozenset(
    {"succeeded", "failed", "skipped", "canceled", "timeout"}
)
_SUPPORTED_TASK_STATES = frozenset(
    {"pending", "running", "canceling", "succeeded", "failed", "canceled", "timeout"}
)


def fail_task_after_execution_process_restart(
    connection: sqlite3.Connection,
    *,
    task_uuid: str,
    now: str | None = None,
) -> bool:
    """原子终结 runtime 重启时仍非终态的工作流任务。

    参数：``connection`` 是调用方持有的工作流写事务；``task_uuid`` 是稳定任务
    UUID；``now`` 是可选统一结算时间。返回：任务自身非终态，或仍含未完成
    Job 并完成失败收敛时为 ``True``；无需收敛的终态任务返回 ``False``。异常：
    任务或作业缺失时抛
    ``StoreNotFound``/``StoreConflict``，SQLite 写入错误原样传播。

    已完成节点保持终态；在途节点失败；未开始节点取消且永不恢复。明确无库存
    变化的中断 Job 释放旧 Claim、Lease 与 Fence；转运/分装虽已物理停止，实际
    物料位置仍可能变化，必须进入 uncertain 并保持占用到库存对账完成。重启前
    已进入物理对账的终态 Job 同样保持占用。
    """

    task = connection.execute(
        "SELECT * FROM workflow_task WHERE uuid = ? AND deleted_at IS NULL",
        (task_uuid,),
    ).fetchone()
    if task is None:
        raise StoreNotFound(f"工作流任务不存在：{task_uuid}")
    jobs = connection.execute(
        """
        SELECT * FROM workflow_node_job
        WHERE workflow_task_uuid = ? AND deleted_at IS NULL
        ORDER BY topological_index ASC, uuid ASC
        """,
        (task_uuid,),
    ).fetchall()
    if not jobs:
        raise StoreConflict(f"工作流任务没有可恢复作业：{task_uuid}")
    task_status = str(task["status"])
    unfinished_jobs = any(
        str(job["status"]) in _IN_FLIGHT_JOB_STATES or str(job["status"]) == "pending"
        for job in jobs
    )
    if task_status not in _SUPPORTED_TASK_STATES:
        raise StoreConflict(f"任务存在无法收敛的重启状态：{task_uuid}/{task_status}")
    if task_status not in {"pending", "running", "canceling"} and not unfinished_jobs:
        return False

    failed_at = now or utc_now()
    failure_details = [
        {
            "code": EXECUTION_PROCESS_RESTARTED,
            "message": "设备执行进程重启，无法继续推进原工作流任务",
        }
    ]
    failure_info = _json(failure_details)
    canceled_details = [
        {
            "code": TASK_ABORTED_BY_RUNTIME_RESTART,
            "message": "runtime 重启导致工作流任务终止，节点未执行",
        }
    ]
    canceled_info = _json(canceled_details)
    # 父 Task 可能已因另一个并行分支失败；此时只终结残留 Job 与锁，不覆盖
    # 原始失败证据。其他状态则由 runtime 重启统一收敛为失败。
    task_error_info = (
        str(task["error_info"] or "[]") if task_status == "failed" else failure_info
    )
    task_finished_at = (
        str(task["finished_at"] or failed_at) if task_status == "failed" else failed_at
    )
    retained_uncertain_jobs = [
        job
        for job in jobs
        if str(job["status"]) in _TERMINAL_JOB_STATES
        and str(job["uncertainty_reason"] or "").strip()
    ]
    restart_settlements: dict[str, TerminalSettlementPlan] = {}
    for job in jobs:
        if str(job["status"]) not in _IN_FLIGHT_JOB_STATES:
            continue
        job_uuid = str(job["uuid"])
        try:
            expected_change_set = decode_json_bytes(
                str(job["expected_change_set"] or "{}").encode("utf-8")
            )
            control_data = decode_json_bytes(
                str(job["control_data"] or "{}").encode("utf-8")
            )
        except (TypeError, ValueError, UnicodeError) as error:
            raise StoreConflict(
                f"重启作业物理结算审计字段已损坏：{job_uuid}"
            ) from error
        if not isinstance(expected_change_set, Mapping) or not isinstance(
            control_data,
            Mapping,
        ):
            raise StoreConflict(f"重启作业物理结算审计字段已损坏：{job_uuid}")
        try:
            restart_settlements[job_uuid] = plan_terminal_settlement(
                outcome="failed",
                return_info={},
                error_info=failure_details,
                expected_change_set=expected_change_set,
                control_data=control_data,
                # dispatched/running/cancel_requested 已越过工作流派发边界；只有
                # Edge 明确提交 local_no_send_proof 才能证明从未物理执行，而该
                # 证明会走标准终态结果路径，不会进入本恢复函数。
                proven_not_started=False,
            )
        except PhysicalSettlementPolicyError as error:
            raise StoreConflict(str(error)) from error
    retained_uncertain_job_uuids = restart_retained_uncertain_job_uuids(jobs) | {
        job_uuid
        for job_uuid, settlement in restart_settlements.items()
        if settlement.hold_claim
    }
    protected_provider_claims = _restart_preheld_provider_claims(
        connection,
        task_uuid=task_uuid,
        jobs=jobs,
        retained_uncertain_job_uuids=retained_uncertain_job_uuids,
    )

    for job in jobs:
        job_uuid = str(job["uuid"])
        status = str(job["status"])
        if status in _IN_FLIGHT_JOB_STATES:
            settlement = restart_settlements[job_uuid]
            changed = connection.execute(
                """
                UPDATE workflow_node_job
                SET status = 'failed', error_info = ?, wait_reason = '{}',
                    control_data = ?, uncertainty_reason = ?,
                    cancel_ack_deadline_at = NULL,
                    cancel_complete_deadline_at = NULL, finished_at = ?,
                    update_time = ?
                WHERE uuid = ?
                  AND status IN (
                      'dispatched', 'running', 'cancel_requested'
                  )
                  AND deleted_at IS NULL
                """,
                (
                    failure_info,
                    encode_json(settlement.control_data, sort_keys=True).decode(
                        "utf-8"
                    ),
                    settlement.uncertainty_reason,
                    failed_at,
                    failed_at,
                    job_uuid,
                ),
            ).rowcount
            if changed != 1:
                raise StoreConflict(f"作业重启失败状态发生并发变化：{job_uuid}")
            record_job_result(
                connection,
                job_row=job,
                outcome="failed",
                return_info={},
                error_info=failure_details,
            )
            _append_job_transition(
                connection,
                task_uuid=task_uuid,
                job_uuid=job_uuid,
                from_status=status,
                to_status="failed",
                now=failed_at,
                data={"failure_code": EXECUTION_PROCESS_RESTARTED},
            )
            close_pending_manual_confirmation(
                connection,
                job_uuid=job_uuid,
                status="canceled",
                decided_at=failed_at,
                resolution_reason="runtime_restarted",
            )
            continue
        if status == "pending":
            changed = connection.execute(
                """
                UPDATE workflow_node_job
                SET status = 'canceled', error_info = ?, wait_reason = '{}',
                    finished_at = ?, update_time = ?
                WHERE uuid = ? AND status = 'pending' AND deleted_at IS NULL
                """,
                (canceled_info, failed_at, failed_at, job_uuid),
            ).rowcount
            if changed != 1:
                raise StoreConflict(f"作业重启取消状态发生并发变化：{job_uuid}")
            _append_job_transition(
                connection,
                task_uuid=task_uuid,
                job_uuid=job_uuid,
                from_status="pending",
                to_status="canceled",
                now=failed_at,
                data={"reason": TASK_ABORTED_BY_RUNTIME_RESTART},
            )
            append_job_state_event(
                connection,
                job_row=job,
                status="canceled",
                details={
                    "error_info": canceled_details,
                    "finished_at": failed_at,
                },
            )
            close_pending_manual_confirmation(
                connection,
                job_uuid=job_uuid,
                status="canceled",
                decided_at=failed_at,
                resolution_reason="runtime_restarted",
            )
            continue
        if status not in _TERMINAL_JOB_STATES:
            raise StoreConflict(f"作业存在无法收敛的重启状态：{job_uuid}/{status}")

    current_jobs = connection.execute(
        "SELECT * FROM workflow_node_job WHERE workflow_task_uuid=? "
        "AND deleted_at IS NULL ORDER BY topological_index, uuid",
        (task_uuid,),
    ).fetchall()
    try:
        execution_plan = decode_json_bytes(
            str(task["execution_plan"] or "{}").encode("utf-8")
        )
    except (TypeError, ValueError, UnicodeError) as error:
        raise StoreConflict("工作流任务资源计划已损坏") from error
    failure_latched_interval_ids = failed_explicit_resource_interval_ids(
        execution_plan if isinstance(execution_plan, Mapping) else {},
        [dict(job) for job in current_jobs],
    )

    for job in jobs:
        job_uuid = str(job["uuid"])
        if job_uuid in retained_uncertain_job_uuids:
            connection.execute(
                """
                UPDATE execution_lock_lease
                SET state = 'uncertain', released_at = NULL, update_time = ?
                WHERE workflow_node_job_uuid = ?
                  AND state IN ('reserved', 'running', 'uncertain')
                  AND deleted_at IS NULL
                """,
                (failed_at, job_uuid),
            )
            connection.execute(
                """
                UPDATE execution_claim
                SET state = 'uncertain', released_at = NULL, update_time = ?
                WHERE workflow_node_job_uuid = ?
                  AND state IN ('reserved', 'running', 'uncertain')
                """,
                (failed_at, job_uuid),
            )
            continue
        if failure_latched_interval_ids:
            release_execution_locks(
                connection,
                job_uuid=job_uuid,
                now=failed_at,
                keep_interval_ids=failure_latched_interval_ids,
            )
            continue
        provider_claims = protected_provider_claims.get(job_uuid)
        if provider_claims:
            for lease in connection.execute(
                """
                SELECT uuid, claim_uuid, lock_key
                FROM execution_lock_lease
                WHERE workflow_node_job_uuid = ?
                  AND state IN ('reserved', 'running', 'uncertain')
                  AND deleted_at IS NULL
                """,
                (job_uuid,),
            ).fetchall():
                claim_uuid = str(lease["claim_uuid"] or "")
                protected_keys = provider_claims.get(claim_uuid, set())
                if str(lease["lock_key"]) in protected_keys:
                    connection.execute(
                        """
                        UPDATE execution_lock_lease
                        SET state='uncertain', released_at=NULL, update_time=?
                        WHERE uuid=?
                          AND state IN ('reserved', 'running', 'uncertain')
                          AND deleted_at IS NULL
                        """,
                        (failed_at, str(lease["uuid"])),
                    )
                    continue
                connection.execute(
                    """
                    UPDATE execution_lock_lease
                    SET state='released', released_at=?, update_time=?
                    WHERE uuid=?
                      AND state IN ('reserved', 'running', 'uncertain')
                      AND deleted_at IS NULL
                    """,
                    (failed_at, failed_at, str(lease["uuid"])),
                )
            protected_claim_uuids = set(provider_claims)
            for claim in connection.execute(
                """
                SELECT claim_uuid FROM execution_claim
                WHERE workflow_node_job_uuid = ?
                  AND state IN ('reserved', 'running', 'uncertain')
                """,
                (job_uuid,),
            ).fetchall():
                claim_uuid = str(claim["claim_uuid"])
                if claim_uuid in protected_claim_uuids:
                    continue
                connection.execute(
                    """
                    UPDATE execution_claim
                    SET state='released', released_at=?, update_time=?
                    WHERE claim_uuid=?
                      AND state IN ('reserved', 'running', 'uncertain')
                    """,
                    (failed_at, failed_at, claim_uuid),
                )
            continue
        connection.execute(
            """
            UPDATE execution_lock_lease
            SET state = 'released', released_at = ?, update_time = ?
            WHERE workflow_node_job_uuid = ?
              AND state IN ('reserved', 'running', 'uncertain')
              AND deleted_at IS NULL
            """,
            (failed_at, failed_at, job_uuid),
        )
        connection.execute(
            """
            UPDATE execution_claim
            SET state = 'released', released_at = ?, update_time = ?
            WHERE workflow_node_job_uuid = ?
              AND state IN ('reserved', 'running', 'uncertain')
            """,
            (failed_at, failed_at, job_uuid),
        )

    connection.execute(
        """
        UPDATE execution_lock_waiter
        SET state = 'released', released_at = ?, update_time = ?
        WHERE workflow_task_uuid = ? AND state = 'waiting'
          AND deleted_at IS NULL
        """,
        (failed_at, failed_at, task_uuid),
    )

    retained_uncertainty_reason = next(
        (
            reason
            for reason in (
                *(
                    str(job["uncertainty_reason"] or "").strip()
                    for job in retained_uncertain_jobs
                ),
                *(
                    str(settlement.uncertainty_reason or "").strip()
                    for settlement in restart_settlements.values()
                ),
            )
            if reason
        ),
        "",
    )
    existing_attention_reason = str(task["attention_reason"] or "").strip()
    retains_physical_resources = bool(retained_uncertain_job_uuids)
    if retains_physical_resources:
        cleanup_status = "requires_attention"
        attention_reason = (
            existing_attention_reason
            or retained_uncertainty_reason
            or "resource_handoff_required"
        )
        control_status = (
            "waiting_reconciliation"
            if retained_uncertainty_reason
            else str(task["control_status"])
        )
        reconciliation_resume_control_status = task[
            "reconciliation_resume_control_status"
        ]
        if (
            retained_uncertainty_reason
            and not reconciliation_resume_control_status
            and str(task["control_status"]) != "waiting_reconciliation"
        ):
            reconciliation_resume_control_status = str(task["control_status"])
    else:
        cleanup_status = "settled"
        attention_reason = None
        control_status = "active"
        reconciliation_resume_control_status = None

    changed_task = connection.execute(
        """
        UPDATE workflow_task
        SET status = 'failed', control_status = ?,
            cleanup_status = ?, attention_reason = ?,
            reconciliation_resume_control_status = ?, wait_reason = '{}',
            error_info = ?, finished_at = ?, update_time = ?
        WHERE uuid = ? AND status = ? AND deleted_at IS NULL
        """,
        (
            control_status,
            cleanup_status,
            attention_reason,
            reconciliation_resume_control_status,
            task_error_info,
            task_finished_at,
            failed_at,
            task_uuid,
            task_status,
        ),
    ).rowcount
    if changed_task != 1:
        raise StoreConflict(f"任务重启失败状态发生并发变化：{task_uuid}")
    if task_status != "failed":
        append_runtime_event(
            connection,
            task_uuid=task_uuid,
            kind="task_transition",
            from_status=task_status,
            to_status="failed",
            data={"failure_code": EXECUTION_PROCESS_RESTARTED},
            now=failed_at,
        )
        append_task_state_event(
            connection,
            task_uuid=task_uuid,
            status="failed",
            details={
                "failure_code": EXECUTION_PROCESS_RESTARTED,
                "cleanup_status": cleanup_status,
                "finished_at": failed_at,
            },
        )
    append_frontend_event(
        connection,
        event="workflow.runtime.changed",
        data={"workflow_task_uuid": task_uuid},
        now=failed_at,
    )
    return True


def restart_retained_uncertain_job_uuids(
    jobs: Sequence[sqlite3.Row | Mapping[str, Any]],
) -> set[str]:
    """识别重启前已经终态、仍等待物理对账的 Job。

    参数：``jobs`` 是 Task 全部 Job 的恢复前或持久聚合快照。返回：已有
    ``uncertainty_reason`` 的终态 Job UUID。异常：无；调用方另行验证其 preheld
    快照，不能把本次 runtime 中断的新失败误判为既有不确定占用。
    """

    def value(job: sqlite3.Row | Mapping[str, Any], field: str) -> Any:
        return job.get(field) if isinstance(job, Mapping) else job[field]

    return {
        str(value(job, "uuid"))
        for job in jobs
        if str(value(job, "status")) in _TERMINAL_JOB_STATES
        and str(value(job, "uncertainty_reason") or "").strip()
    }


def _restart_preheld_provider_claims(
    connection: sqlite3.Connection,
    *,
    task_uuid: str,
    jobs: Sequence[sqlite3.Row],
    retained_uncertain_job_uuids: set[str],
) -> dict[str, dict[str, set[str]]]:
    """定位真正支撑 retained Job 的 provider Claim/Lease。

    返回 ``provider_job_uuid -> claim_uuid -> lock_keys``；没有依赖时返回空映射。
    快照、Claim、Fence 或活动 Lease 无法相互证明时抛 ``StoreConflict``，使调用
    方在任何终态写入前回滚。provider 的其他锁不在返回值中，可按 runtime 已
    停止语义释放。
    """

    if not retained_uncertain_job_uuids:
        return {}
    jobs_by_uuid = {str(job["uuid"]): job for job in jobs}
    protected: dict[str, dict[str, set[str]]] = {}

    def corrupted(job_uuid: str, detail: str) -> StoreConflict:
        return StoreConflict(f"重启 preheld 权威事实损坏：{job_uuid}/{detail}")

    for job_uuid in sorted(retained_uncertain_job_uuids):
        job = jobs_by_uuid[job_uuid]
        try:
            control_data = decode_json_bytes(
                str(job["control_data"] or "{}").encode("utf-8")
            )
        except (TypeError, ValueError, UnicodeError) as error:
            raise corrupted(job_uuid, "control_data") from error
        if not isinstance(control_data, dict):
            raise corrupted(job_uuid, "control_data")
        raw_provider_job_uuids = control_data.get(
            "dispatch_preheld_job_uuids", []
        )
        raw_preheld_lock_keys = control_data.get("dispatch_preheld_lock_keys", [])
        if (
            not isinstance(raw_provider_job_uuids, list)
            or not isinstance(raw_preheld_lock_keys, list)
            or any(
                not isinstance(value, str) for value in raw_provider_job_uuids
            )
            or any(not isinstance(value, str) for value in raw_preheld_lock_keys)
        ):
            raise corrupted(job_uuid, "preheld_snapshot")
        provider_job_uuids = {
            value.strip() for value in raw_provider_job_uuids if value.strip()
        }
        preheld_lock_keys = {
            value.strip() for value in raw_preheld_lock_keys if value.strip()
        }
        if (
            len(provider_job_uuids) != len(raw_provider_job_uuids)
            or len(preheld_lock_keys) != len(raw_preheld_lock_keys)
            or job_uuid in provider_job_uuids
            or (preheld_lock_keys and not provider_job_uuids)
            or not provider_job_uuids <= set(jobs_by_uuid)
        ):
            raise corrupted(job_uuid, "preheld_snapshot")

        retained_claim = connection.execute(
            """
            SELECT claim_uuid, workflow_task_uuid, resource_keys, state, released_at
            FROM execution_claim
            WHERE workflow_node_job_uuid=?
            ORDER BY attempt DESC LIMIT 1
            """,
            (job_uuid,),
        ).fetchone()
        if (
            retained_claim is None
            or str(retained_claim["workflow_task_uuid"]) != task_uuid
            or str(retained_claim["state"])
            not in {"reserved", "running", "uncertain"}
            or retained_claim["released_at"] is not None
        ):
            raise corrupted(job_uuid, "retained_claim")
        try:
            retained_resource_keys = decode_json_bytes(
                str(retained_claim["resource_keys"]).encode("utf-8")
            )
        except (TypeError, ValueError, UnicodeError) as error:
            raise corrupted(job_uuid, "retained_claim_resources") from error
        if (
            not isinstance(retained_resource_keys, list)
            or any(
                not isinstance(value, str) or not value.strip()
                for value in retained_resource_keys
            )
            or len({value.strip() for value in retained_resource_keys})
            != len(retained_resource_keys)
            or not preheld_lock_keys
            <= {value.strip() for value in retained_resource_keys}
        ):
            raise corrupted(job_uuid, "retained_claim_resources")
        retained_keys = {value.strip() for value in retained_resource_keys}

        raw_dispatch_fences = control_data.get("dispatch_fences")
        authoritative_fences: dict[str, int] | None = None
        if raw_dispatch_fences is None:
            if preheld_lock_keys or str(job["dispatch_effect_uuid"] or "").strip():
                raise corrupted(job_uuid, "missing_dispatch_fences")
        else:
            if not isinstance(raw_dispatch_fences, list):
                raise corrupted(job_uuid, "dispatch_fences")
            authoritative_fences = {}
            for raw_fence in raw_dispatch_fences:
                if not isinstance(raw_fence, dict) or set(raw_fence) != {
                    "lock_key",
                    "fencing_token",
                }:
                    raise corrupted(job_uuid, "dispatch_fences")
                lock_key = str(raw_fence["lock_key"] or "").strip()
                token = raw_fence["fencing_token"]
                if (
                    not lock_key
                    or isinstance(token, bool)
                    or not isinstance(token, int)
                    or token <= 0
                    or lock_key in authoritative_fences
                ):
                    raise corrupted(job_uuid, "dispatch_fences")
                authoritative_fences[lock_key] = token
            if set(authoritative_fences) != retained_keys:
                raise corrupted(job_uuid, "dispatch_fences")

        active_owned_keys: set[str] = set()
        for owned in connection.execute(
            """
            SELECT lock_key, workflow_task_uuid, workflow_node_job_uuid,
                   state, released_at, fencing_token
            FROM execution_lock_lease
            WHERE claim_uuid=?
              AND state IN ('reserved', 'running', 'uncertain')
              AND deleted_at IS NULL
            """,
            (str(retained_claim["claim_uuid"]),),
        ).fetchall():
            lock_key = str(owned["lock_key"])
            token = owned["fencing_token"]
            if (
                lock_key in active_owned_keys
                or lock_key not in retained_keys
                or str(owned["workflow_task_uuid"]) != task_uuid
                or str(owned["workflow_node_job_uuid"]) != job_uuid
                or str(owned["state"])
                not in {"reserved", "running", "uncertain"}
                or owned["released_at"] is not None
                or token is None
                or isinstance(token, bool)
                or int(token) <= 0
                or (
                    authoritative_fences is not None
                    and int(token) != authoritative_fences[lock_key]
                )
            ):
                raise corrupted(job_uuid, f"retained_lease:{lock_key}")
            active_owned_keys.add(lock_key)
        missing_owned_keys = retained_keys - preheld_lock_keys - active_owned_keys
        if missing_owned_keys:
            raise corrupted(
                job_uuid,
                "missing_retained_leases:" + ",".join(sorted(missing_owned_keys)),
            )
        if not preheld_lock_keys:
            continue

        for lock_key in sorted(preheld_lock_keys):
            owners = connection.execute(
                """
                SELECT lease.uuid AS lease_uuid,
                       lease.workflow_node_job_uuid, lease.claim_uuid,
                       lease.state AS lease_state, lease.released_at,
                       lease.fencing_token, lease.meta_data,
                       claim.workflow_task_uuid AS claim_task_uuid,
                       claim.workflow_node_job_uuid AS claim_job_uuid,
                       claim.state AS claim_state,
                       claim.resource_keys AS claim_resource_keys,
                       claim.released_at AS claim_released_at
                FROM execution_lock_lease AS lease
                JOIN execution_claim AS claim
                  ON claim.claim_uuid=lease.claim_uuid
                WHERE lease.workflow_task_uuid=? AND lease.lock_key=?
                  AND lease.state IN ('reserved', 'running', 'uncertain')
                  AND lease.deleted_at IS NULL
                """,
                (task_uuid, lock_key),
            ).fetchall()
            if len(owners) != 1:
                raise corrupted(job_uuid, f"active_owner:{lock_key}")
            owner = owners[0]
            owner_job_uuid = str(owner["workflow_node_job_uuid"])
            if authoritative_fences is None:  # 已由 preheld 快照校验排除。
                raise corrupted(job_uuid, "missing_dispatch_fences")
            expected_fence = authoritative_fences[lock_key]
            if (
                str(owner["claim_task_uuid"]) != task_uuid
                or str(owner["claim_job_uuid"]) != owner_job_uuid
                or str(owner["lease_state"])
                not in {"reserved", "running", "uncertain"}
                or str(owner["claim_state"])
                not in {"reserved", "running", "uncertain"}
                or owner["released_at"] is not None
                or owner["claim_released_at"] is not None
                or owner["fencing_token"] is None
                or int(owner["fencing_token"]) != expected_fence
            ):
                raise corrupted(job_uuid, f"active_owner:{lock_key}")
            try:
                metadata = decode_json_bytes(
                    str(owner["meta_data"] or "{}").encode("utf-8")
                )
            except (TypeError, ValueError, UnicodeError) as error:
                raise corrupted(job_uuid, f"lease_metadata:{lock_key}") from error
            if not isinstance(metadata, dict):
                raise corrupted(job_uuid, f"lease_metadata:{lock_key}")
            if owner_job_uuid == job_uuid:
                if (
                    str(owner["claim_uuid"])
                    != str(retained_claim["claim_uuid"])
                    or str(metadata.get("acquired_by_job_uuid") or "")
                    != job_uuid
                    or str(metadata.get("handoff_from_job_uuid") or "")
                    not in provider_job_uuids
                ):
                    raise corrupted(job_uuid, f"retained_owner:{lock_key}")
                continue
            if (
                owner_job_uuid not in provider_job_uuids
            ):
                raise corrupted(job_uuid, f"provider_owner:{lock_key}")
            try:
                owner_resource_keys = decode_json_bytes(
                    str(owner["claim_resource_keys"]).encode("utf-8")
                )
            except (TypeError, ValueError, UnicodeError) as error:
                raise corrupted(job_uuid, f"provider_claim:{lock_key}") from error
            normalized_owner_keys = (
                {value.strip() for value in owner_resource_keys}
                if isinstance(owner_resource_keys, list)
                and all(isinstance(value, str) for value in owner_resource_keys)
                else set()
            )
            if (
                not isinstance(owner_resource_keys, list)
                or any(
                    not isinstance(value, str) or not value.strip()
                    for value in owner_resource_keys
                )
                or len(normalized_owner_keys) != len(owner_resource_keys)
                or lock_key not in normalized_owner_keys
                or str(metadata.get("acquired_by_job_uuid") or "")
                != owner_job_uuid
            ):
                raise corrupted(job_uuid, f"provider_claim:{lock_key}")
            claim_uuid = str(owner["claim_uuid"])
            protected.setdefault(owner_job_uuid, {}).setdefault(
                claim_uuid, set()
            ).add(lock_key)
    return protected


def _append_job_transition(
    connection: sqlite3.Connection,
    *,
    task_uuid: str,
    job_uuid: str,
    from_status: str,
    to_status: str,
    now: str,
    data: dict[str, Any],
) -> None:
    """追加单个重启导致的作业状态转换日志。

    参数：``connection`` 是当前事务；Task/Job UUID 定位聚合与节点作业；两个状态
    是转换前后 wire 值；``now`` 是统一时间；``data`` 是稳定诊断对象。返回无。
    异常：日志写入错误原样传播并回滚调用方事务。
    """

    append_runtime_event(
        connection,
        task_uuid=task_uuid,
        job_uuid=job_uuid,
        kind="job_transition",
        from_status=from_status,
        to_status=to_status,
        data=data,
        now=now,
    )


def _json(value: Sequence[dict[str, str]]) -> str:
    """把失败详情编码为键稳定的 JSON 文本。

    参数：``value`` 是结构化错误对象序列。返回：UTF-8 JSON 文本。异常：不可编码
    值由 JSON 编码器原样抛出，禁止写入部分恢复事实。
    """

    return encode_json(value, sort_keys=True).decode("utf-8")


__all__ = [
    "EXECUTION_PROCESS_RESTARTED",
    "TASK_ABORTED_BY_RUNTIME_RESTART",
    "fail_task_after_execution_process_restart",
    "restart_retained_uncertain_job_uuids",
]
