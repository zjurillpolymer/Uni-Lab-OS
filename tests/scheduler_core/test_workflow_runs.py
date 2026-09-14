"""多 WorkflowRun 的 Scheduler 提交、并发和身份隔离合同。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from unilabos.app.scheduler.api import create_scheduler_router
from unilabos.app.scheduler.dispatch import RecordingDispatcher
from unilabos.app.scheduler.models import WorkflowEdge, WorkflowNode, WorkflowSpec
from unilabos.app.scheduler.service import EdgeScheduler


def _spec(workflow_id: str, run_id: str, device_id: str) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        run_id=run_id,
        task_id="caller-task",
        nodes=[
            WorkflowNode(
                id="take",
                device_id=device_id,
                action_name="take",
                param={"sample": run_id},
            ),
            WorkflowNode(
                id="dose",
                device_id=device_id,
                action_name="dose",
            ),
        ],
        edges=[
            WorkflowEdge(
                uuid=f"{workflow_id}:take-dose",
                source_node_id="take",
                target_node_id="dose",
            )
        ],
    )


def test_multiple_runs_share_task_and_dispatch_on_independent_devices() -> None:
    dispatcher = RecordingDispatcher()
    scheduler = EdgeScheduler(dispatcher=dispatcher)
    specs = [_spec("wf-a", "run-a", "device-a"), _spec("wf-b", "run-b", "device-b")]

    result = scheduler.submit_workflow_runs(specs, task_id="task-001")

    assert result["task_id"] == "task-001"
    assert {item["run_id"] for item in result["runs"]} == {"run-a", "run-b"}
    assert {item["task_id"] for item in dispatcher.dispatched} == {"task-001"}
    assert {item["run_id"] for item in dispatcher.dispatched} == {"run-a", "run-b"}

    for payload in list(dispatcher.dispatched):
        scheduler.on_job_finished(payload["job_id"], True, {"ok": True})
    assert {item["run_id"] for item in dispatcher.dispatched[2:]} == {"run-a", "run-b"}


def test_shared_device_serializes_runs_but_keeps_each_run_dag() -> None:
    dispatcher = RecordingDispatcher()
    scheduler = EdgeScheduler(dispatcher=dispatcher)
    scheduler.submit_workflow_runs(
        [_spec("wf-a", "run-a", "shared"), _spec("wf-b", "run-b", "shared")],
        task_id="task-002",
    )

    assert len(dispatcher.dispatched) == 1
    first = dispatcher.dispatched[0]
    scheduler.on_job_finished(first["job_id"], True, {})
    assert len(dispatcher.dispatched) == 2
    assert dispatcher.dispatched[1]["node_id"] == "dose"
    assert dispatcher.dispatched[1]["run_id"] == first["run_id"]


def test_duplicate_run_id_is_rejected_without_registering_any_member() -> None:
    scheduler = EdgeScheduler(dispatcher=RecordingDispatcher())
    with pytest.raises(ValueError, match="unique run_id"):
        scheduler.submit_workflow_runs(
            [_spec("wf-a", "same", "device-a"), _spec("wf-b", "same", "device-b")],
            task_id="task-003",
        )
    assert scheduler.snapshot()["workflows"] == {}


def test_workflow_runs_http_endpoint_accepts_per_run_parameters() -> None:
    dispatcher = RecordingDispatcher()
    scheduler = EdgeScheduler(dispatcher=dispatcher)
    app = FastAPI()
    app.include_router(create_scheduler_router(lambda: scheduler))

    response = TestClient(app).post(
        "/api/v1/workflow-runs",
        json={
            "task_id": "task-http",
            "runs": [
                {
                    "workflow_id": "wf-http-a",
                    "run_id": "run-http-a",
                    "task_id": "ignored-by-group",
                    "nodes": [
                        {
                            "id": "mix",
                            "device_id": "device-a",
                            "action_name": "mix",
                            "param": {"volume_ml": 100},
                        }
                    ],
                },
                {
                    "workflow_id": "wf-http-b",
                    "run_id": "run-http-b",
                    "nodes": [
                        {
                            "id": "mix",
                            "device_id": "device-b",
                            "action_name": "mix",
                            "param": {"volume_ml": 200},
                        }
                    ],
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task-http"
    assert {item["run_id"] for item in payload["runs"]} == {
        "run-http-a",
        "run-http-b",
    }
    assert {item["run_id"] for item in payload["dispatched"]} == {
        "run-http-a",
        "run-http-b",
    }
