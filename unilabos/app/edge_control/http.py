"""生产 Edge 协议的 HTTP 事实数据面。"""

from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

import requests

from unilabos.app.edge_control.store import StoredJob
from unilabos.utils.tracing import inject_trace_context, span


BACKEND_UNAUTHORIZED_BUSINESS_CODE = 1001


class EdgeProtocolHTTPError(RuntimeError):
    """后端拒绝 Edge 数据面请求。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        business_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.business_code = business_code


class EdgeDataPlane:
    """分离工站调度事实与上游物料查询的 HTTP 数据面。"""

    def __init__(
        self,
        backend_address: str,
        scheduler_address: str,
        api_key: str,
        backend_api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """冻结两个 HTTP 权威地址及其独立凭据。

        参数：Backend 地址只用于全局物料查询；调度地址承载作业、反馈和结果；
        两个凭据分别鉴权，``timeout`` 是请求预算。返回无；非法 URL 在请求前由
        ``_api_base`` 拒绝，网络异常由具体调用原样传播。
        """

        self.backend_api = _api_base(backend_address)
        self.scheduler_api = _api_base(scheduler_address)
        self.api_key = api_key
        self.backend_api_key = str(backend_api_key or api_key)
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {api_key}"})
        self._lock = threading.Lock()

    def register_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"{self.scheduler_api}/edge/sessions",
            span_name="edge.http.session.register",
            http_route="/api/v1/edge/sessions",
            json=payload,
        )

    def report_error_decision_required(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """上报一个等待人工选择的动作异常。"""

        return self._request(
            "POST",
            f"{self.scheduler_api}/edge/error-decisions",
            span_name="edge.http.error_decision.report",
            http_route="/api/v1/edge/error-decisions",
            json=payload,
        )

    def update_device_status(
        self,
        session_uuid: str,
        local_device_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """提交当前 Edge 会话中一个设备的实时可派发事实。"""

        return self._request(
            "PUT",
            f"{self.scheduler_api}/edge/sessions/{quote(session_uuid, safe='')}"
            f"/devices/{quote(local_device_id, safe='')}/status",
            span_name="edge.http.device.status.update",
            http_route="/api/v1/edge/sessions/:session_uuid/devices/:device_id/status",
            json=payload,
        )

    def material_uuids_by_barcode(
        self, barcodes: Iterable[str]
    ) -> Dict[str, str]:
        """从正式 Backend 解析本次注册涉及的设备物料身份。"""

        wanted = {str(barcode).strip() for barcode in barcodes if str(barcode).strip()}
        resolved: Dict[str, str] = {}
        page = 1
        while wanted - resolved.keys():
            result = self._request(
                "GET",
                f"{self.backend_api}/materials",
                span_name="edge.http.material.list",
                http_route="/api/v1/materials",
                params={
                    "page": page,
                    "page_size": 100,
                    "with_children": "true",
                },
                api_key=self.backend_api_key,
            )
            items = result.get("items")
            if not isinstance(items, list):
                raise EdgeProtocolHTTPError("GET /materials returned invalid items")
            for item in items:
                if not isinstance(item, dict):
                    continue
                barcode = str(item.get("barcode") or "").strip()
                material_uuid = str(item.get("uuid") or "").strip()
                if barcode in wanted and material_uuid:
                    resolved[barcode] = material_uuid
            total = int(result.get("total") or 0)
            if not items or page * 100 >= total:
                break
            page += 1
        return resolved

    def fetch_job(self, job: StoredJob) -> Dict[str, Any]:
        """从本地工站调度权威读取一个作业的实际执行载荷。

        参数：``job`` 是 WebSocket 已持久化的作业镜像。返回 HTTP 事实对象；
        身份或鉴权冲突由统一请求边界抛 ``EdgeProtocolHTTPError``。
        """

        return self._request(
            "GET",
            f"{self.scheduler_api}/edge/jobs/{job.job_uuid}",
            span_name="edge.http.job.fetch",
            http_route="/api/v1/edge/jobs/:job_uuid",
            params={"task_uuid": job.task_uuid, "node_uuid": job.node_uuid},
            headers=_job_headers(job),
        )

    def commit_feedback(
        self,
        job: StoredJob,
        sequence: int,
        feedback_type: str,
        feedback: Dict[str, Any],
        observed_at: str,
    ) -> Dict[str, Any]:
        """提交带完整执行尝试身份的作业反馈。"""

        return self._request(
            "POST",
            f"{self.scheduler_api}/edge/jobs/{job.job_uuid}/feedback",
            span_name="edge.http.job.feedback.commit",
            http_route="/api/v1/edge/jobs/:job_uuid/feedback",
            headers=_job_headers(job),
            json={
                **_job_attempt_identity(job),
                "sequence": sequence,
                "feedback_type": feedback_type,
                "data": feedback,
                "observed_at": observed_at,
                "idempotency_key": f"{job.job_uuid}:feedback:{sequence}",
            },
        )

    def commit_outcome(
        self,
        job: StoredJob,
        outcome: str,
        return_info: Dict[str, Any],
        error_info: List[Dict[str, Any]],
        unknown_command_ids: Optional[List[str]] = None,
        inventory_consumptions: Optional[List[Dict[str, Any]]] = None,
        material_aliquot_receipts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """提交作业结果以及仍待对账恢复的物理命令身份。

        ``job`` 提供 Backend 工作流节点作业（WorkflowNodeJob）、
        工作流任务（WorkflowTask）、节点和命令身份；``outcome``、
        ``return_info`` 与 ``error_info`` 描述 Edge 观察结果；
        ``unknown_command_ids`` 标识尚未完成物理结算（PhysicalSettlement）的
        设备命令。返回 Backend 的持久结果对象；鉴权、冲突和传输错误由
        :meth:`_request` 以 ``EdgeProtocolHTTPError`` 抛出。固定
        ``Idempotency-Key`` 使同一作业的重试只创建一个结果。
        """

        headers = _job_headers(job)
        headers["Idempotency-Key"] = f"{job.job_uuid}:outcome:v1"
        return self._request(
            "PUT",
            f"{self.scheduler_api}/edge/jobs/{job.job_uuid}/outcome",
            span_name="edge.http.job.outcome.commit",
            http_route="/api/v1/edge/jobs/:job_uuid/outcome",
            headers=headers,
            json={
                **_job_attempt_identity(job),
                "outcome": outcome,
                "return_info": return_info,
                "error_info": error_info,
                "unknown_command_ids": unknown_command_ids or [],
                "inventory_consumptions": inventory_consumptions or [],
                "material_aliquot_receipts": material_aliquot_receipts or [],
            },
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        span_name: str,
        http_route: str,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """执行一次带追踪和指定权威凭据的 JSON HTTP 请求。

        参数：方法、URL、追踪名和路由标识描述请求；``api_key`` 可切换上游凭据；
        其余参数传给 requests。返回业务 ``data`` 对象。异常：非 JSON、非成功 HTTP
        或业务错误转为 ``EdgeProtocolHTTPError``，网络异常原样传播。
        """

        kwargs.setdefault("timeout", self.timeout)
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Authorization", f"Bearer {api_key or self.api_key}")
        with span(
            span_name,
            kind="client",
            attributes={
                "http.request.method": method,
                "http.route": http_route,
            },
        ):
            carrier: Dict[str, Any] = {}
            inject_trace_context(carrier)
            # OTel 关闭时只有本地 trace_id；开启时同时保留 W3C 载体。
            for key in ("trace_id", "traceparent", "tracestate"):
                if carrier.get(key):
                    headers[key] = str(carrier[key])
            if headers:
                kwargs["headers"] = headers
            with self._lock:
                response = self._session.request(method, url, **kwargs)
            try:
                payload = response.json()
            except ValueError as exc:
                raise EdgeProtocolHTTPError(
                    f"{method} {url} returned non-JSON HTTP {response.status_code}",
                    status_code=response.status_code,
                ) from exc
            if response.status_code < 200 or response.status_code >= 300:
                raise EdgeProtocolHTTPError(
                    f"{method} {url} returned HTTP {response.status_code}: {payload}",
                    status_code=response.status_code,
                )
            if not isinstance(payload, dict):
                raise EdgeProtocolHTTPError(
                    f"{method} {url} returned a non-object payload"
                )
            if "code" in payload and int(payload.get("code") or 0) != 0:
                business_code = int(payload.get("code") or 0)
                raise EdgeProtocolHTTPError(
                    f"{method} {url} returned business error {business_code}: "
                    f"{payload.get('error')}",
                    business_code=business_code,
                )
            result = payload.get("data", payload)
            if not isinstance(result, dict):
                raise EdgeProtocolHTTPError(f"{method} {url} returned invalid data")
            return result


def _job_attempt_identity(job: StoredJob) -> Dict[str, Any]:
    """把 Edge 镜像中的执行尝试身份投影到 HTTP 事实载荷。"""

    return {
        "job_uuid": job.job_uuid,
        "task_uuid": job.task_uuid,
        "node_uuid": job.node_uuid,
        "command_uuid": job.command_uuid,
        "claim_uuid": job.claim_uuid,
        "attempt": job.attempt,
        "fences": [
            {"lock_key": lock_key, "fencing_token": fencing_token}
            for lock_key, fencing_token in job.fences
        ],
    }


def _job_headers(job: StoredJob) -> Dict[str, str]:
    return {
        "X-Command-UUID": job.command_uuid,
        "X-Job-Token": job.job_access_token,
    }


def _api_base(address: str) -> str:
    base = str(address or "").strip().rstrip("/")
    if not base:
        raise ValueError("Edge protocol address is required")
    for suffix in ("/api/v1/edge/ws", "/api/v1/ws/schedule"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if base.endswith("/api/v1"):
        return base
    return f"{base}/api/v1"


def websocket_url(scheduler_address: str) -> str:
    api = _api_base(scheduler_address)
    if api.startswith("https://"):
        return "wss://" + api[len("https://") :] + "/edge/ws"
    if api.startswith("http://"):
        return "ws://" + api[len("http://") :] + "/edge/ws"
    if api.startswith("wss://"):
        return api + "/edge/ws"
    if api.startswith("ws://"):
        return api + "/edge/ws"
    raise ValueError("scheduler address must use http(s) or ws(s)")
