"""F07 组合工作流调用（CompositeWorkflowInvocation）平面执行计划合同。"""

from __future__ import annotations

from typing import Any

import pytest

from unilabos.workflow._execution_plan_graph import (
    ExecutionPlanBuildError,
    ExecutionPlanGraphNormalizer,
)
from unilabos.workflow.execution_plan import ExecutionPlanBuilder
from unilabos.workflow.task_input import prepare_task_input

WORKFLOW_UUID = "71000000-0000-4000-8000-000000000001"
PRODUCER_UUID = "71000000-0000-4000-8000-000000000002"
INVOCATION_UUID = "71000000-0000-4000-8000-000000000003"
INTERNAL_UUID = "71000000-0000-4000-8000-000000000004"
CONSUMER_UUID = "71000000-0000-4000-8000-000000000005"
SECOND_INVOCATION_UUID = "71000000-0000-4000-8000-000000000006"
SECOND_INTERNAL_UUID = "71000000-0000-4000-8000-000000000007"
PRODUCER_TEMPLATE = "72000000-0000-4000-8000-000000000001"
INVOCATION_TEMPLATE = "72000000-0000-4000-8000-000000000002"
INTERNAL_TEMPLATE = "72000000-0000-4000-8000-000000000003"
CONSUMER_TEMPLATE = "72000000-0000-4000-8000-000000000004"
PRODUCER_SOURCE = "73000000-0000-4000-8000-000000000001"
INVOCATION_TARGET = "73000000-0000-4000-8000-000000000002"
INVOCATION_SOURCE = "73000000-0000-4000-8000-000000000003"
INTERNAL_TARGET = "73000000-0000-4000-8000-000000000004"
INTERNAL_READY = "73000000-0000-4000-8000-000000000005"
CONSUMER_TARGET = "73000000-0000-4000-8000-000000000006"
REPEAT_REGION_UUID = "71000000-0000-4000-8000-000000000008"


def _node(
    uuid: str,
    template_uuid: str,
    *,
    node_type: str = "compute",
    param: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造一个最小冻结节点；参数定位身份、模板、类型和可选静态参数。"""

    return {
        "uuid": uuid,
        "workflow_node_template_uuid": template_uuid,
        "name": uuid,
        "type": node_type,
        "pose": {},
        "param": param or {},
        "execution_policy": {},
        "disabled": False,
        "minimized": False,
        "meta_data": {"unilab": {"input_bindings": {}}},
    }


def _handle(
    uuid: str,
    template_uuid: str,
    *,
    io_type: str,
    key: str,
    data_source: str,
    required: bool,
) -> dict[str, Any]:
    """构造整数连接点（Handle）；参数给出端点身份与值来源语义。"""

    return {
        "uuid": uuid,
        "workflow_node_template_uuid": template_uuid,
        "handle_key": key,
        "io_type": io_type,
        "type": "integer",
        "required": required,
        "data_source": data_source,
        "data_key": key,
        "meta_data": {"unilab": {"value_schema": {"type": "integer"}}},
    }


def _edge(
    uuid: str,
    source_node_uuid: str,
    source_handle_uuid: str,
    target_node_uuid: str,
    target_handle_uuid: str,
) -> dict[str, str]:
    """构造一条冻结工作流边；参数完整指定来源和目标端点。"""

    return {
        "uuid": uuid,
        "source_node_uuid": source_node_uuid,
        "source_handle_uuid": source_handle_uuid,
        "target_node_uuid": target_node_uuid,
        "target_handle_uuid": target_handle_uuid,
    }


def _composite_node(
    *,
    static_value: int | None = None,
    invocation_uuid: str = INVOCATION_UUID,
    internal_uuid: str = INTERNAL_UUID,
) -> dict[str, Any]:
    """构造带参数透传输出和完成边界的组合调用节点。

    参数：``static_value`` 是可选节点固定值；``invocation_uuid`` 是组合调用稳定
    身份；``internal_uuid`` 是本次展开的内部节点身份。返回：供公开执行计划编译器
    使用的完整节点。异常：无；测试调用方负责提供符合 UUID 合同的身份。
    """

    node = _node(
        invocation_uuid,
        INVOCATION_TEMPLATE,
        node_type="workflow",
        param={} if static_value is None else {"value": static_value},
    )
    node["meta_data"]["unilab"]["composite"] = {
        "target_mappings": {
            INVOCATION_TARGET: [
                {
                    "workflow_node_uuid": internal_uuid,
                    "target_handle_uuid": INTERNAL_TARGET,
                }
            ]
        },
        "source_mappings": {
            INVOCATION_SOURCE: {"kind": "workflow_input", "parameter": "value"}
        },
        "structural_mappings": {
            "entry_targets": [
                {
                    "workflow_node_uuid": internal_uuid,
                    "target_handle_uuid": INTERNAL_TARGET,
                }
            ],
            "completion_sources": [
                {
                    "workflow_node_uuid": internal_uuid,
                    "source_handle_uuid": INTERNAL_READY,
                }
            ],
        },
        "contract_compatibility": {
            "parameters": [
                {
                    "name": "value",
                    "handle_uuid": INVOCATION_TARGET,
                    "schema": {"type": "integer"},
                    "required": True,
                    "has_default": False,
                }
            ]
        },
    }
    return node


def _handles() -> list[dict[str, Any]]:
    """返回生产者、组合边界、内部动作和消费者使用的完整端点集合。"""

    return [
        _handle(
            PRODUCER_SOURCE,
            PRODUCER_TEMPLATE,
            io_type="source",
            key="value",
            data_source="result",
            required=False,
        ),
        _handle(
            INVOCATION_TARGET,
            INVOCATION_TEMPLATE,
            io_type="target",
            key="value",
            data_source="executor",
            required=True,
        ),
        _handle(
            INVOCATION_SOURCE,
            INVOCATION_TEMPLATE,
            io_type="source",
            key="value",
            data_source="result",
            required=False,
        ),
        _handle(
            INTERNAL_TARGET,
            INTERNAL_TEMPLATE,
            io_type="target",
            key="value",
            data_source="executor",
            required=True,
        ),
        _handle(
            INTERNAL_READY,
            INTERNAL_TEMPLATE,
            io_type="source",
            key="ready",
            data_source="status",
            required=False,
        ),
        _handle(
            CONSUMER_TARGET,
            CONSUMER_TEMPLATE,
            io_type="target",
            key="value",
            data_source="executor",
            required=True,
        ),
    ]


def test_result_source_remains_value_provider_in_frozen_plan() -> None:
    """动作 result 输出必须提供值，不能被降级为纯依赖边。"""

    graph = {
        "workflow": {
            "uuid": WORKFLOW_UUID,
            "revision": 1,
            "name": "result value",
            "tags": [],
            "meta_data": {
                "unilab": {
                    "input_contract": {"version": 1, "parameters": []},
                    "output_contract": {"version": 1, "outputs": []},
                    "output_bindings": {},
                }
            },
        },
        "nodes": [
            _node(PRODUCER_UUID, PRODUCER_TEMPLATE, param={"seed": 1}),
            _node(CONSUMER_UUID, CONSUMER_TEMPLATE),
        ],
        "edges": [
            _edge(
                "74000000-0000-4000-8000-000000000001",
                PRODUCER_UUID,
                PRODUCER_SOURCE,
                CONSUMER_UUID,
                CONSUMER_TARGET,
            )
        ],
        "node_templates": [
            {"uuid": PRODUCER_TEMPLATE, "node_type": "compute", "type": "compute"},
            {"uuid": CONSUMER_TEMPLATE, "node_type": "compute", "type": "compute"},
        ],
        "handle_templates": [
            _handles()[0],
            _handles()[-1],
        ],
    }

    plan, jobs = ExecutionPlanBuilder().build(
        graph, run_mode="normal", target_node_uuid=None
    )
    prepared = prepare_task_input(
        graph=graph,
        raw_input={},
        execution_plan=plan,
        jobs=jobs,
    )

    assert plan["edges"][0].get("dependency_only") is not True
    assert len(prepared.jobs) == 2


def test_composite_passthrough_flattens_value_and_completion_edges() -> None:
    """组合透传值须进入内部动作和下游，同时保留完成顺序依赖。"""

    nodes = {
        node["uuid"]: node
        for node in (
            _node(PRODUCER_UUID, PRODUCER_TEMPLATE),
            _composite_node(),
            _node(INTERNAL_UUID, INTERNAL_TEMPLATE),
            _node(CONSUMER_UUID, CONSUMER_TEMPLATE),
        )
    }
    handles = {handle["uuid"]: handle for handle in _handles()}
    edges = [
        _edge(
            "74000000-0000-4000-8000-000000000002",
            PRODUCER_UUID,
            PRODUCER_SOURCE,
            INVOCATION_UUID,
            INVOCATION_TARGET,
        ),
        _edge(
            "74000000-0000-4000-8000-000000000003",
            INVOCATION_UUID,
            INVOCATION_SOURCE,
            CONSUMER_UUID,
            CONSUMER_TARGET,
        ),
    ]

    flattened, params = ExecutionPlanGraphNormalizer().flatten_composite_edges(
        nodes=nodes,
        edges=edges,
        handles=handles,
    )

    endpoints = {
        (
            edge["source_node_uuid"],
            edge["source_handle_uuid"],
            edge["target_node_uuid"],
            edge["target_handle_uuid"],
        )
        for edge in flattened
    }
    assert endpoints == {
        (PRODUCER_UUID, PRODUCER_SOURCE, INTERNAL_UUID, INTERNAL_TARGET),
        (PRODUCER_UUID, PRODUCER_SOURCE, CONSUMER_UUID, CONSUMER_TARGET),
        (INTERNAL_UUID, INTERNAL_READY, CONSUMER_UUID, CONSUMER_TARGET),
    }
    assert params == {}


def test_chained_composite_passthrough_counts_only_value_provider() -> None:
    """连续组合调用须保留完成边，但不得把它误算成第二个值提供者。"""

    nodes = {
        node["uuid"]: node
        for node in (
            _node(PRODUCER_UUID, PRODUCER_TEMPLATE),
            _composite_node(),
            _node(INTERNAL_UUID, INTERNAL_TEMPLATE),
            _composite_node(
                invocation_uuid=SECOND_INVOCATION_UUID,
                internal_uuid=SECOND_INTERNAL_UUID,
            ),
            _node(SECOND_INTERNAL_UUID, INTERNAL_TEMPLATE),
            _node(CONSUMER_UUID, CONSUMER_TEMPLATE),
        )
    }
    handles = {handle["uuid"]: handle for handle in _handles()}
    flattened, params = ExecutionPlanGraphNormalizer().flatten_composite_edges(
        nodes=nodes,
        edges=[
            _edge(
                "74000000-0000-4000-8000-000000000005",
                PRODUCER_UUID,
                PRODUCER_SOURCE,
                INVOCATION_UUID,
                INVOCATION_TARGET,
            ),
            _edge(
                "74000000-0000-4000-8000-000000000006",
                INVOCATION_UUID,
                INVOCATION_SOURCE,
                SECOND_INVOCATION_UUID,
                INVOCATION_TARGET,
            ),
            _edge(
                "74000000-0000-4000-8000-000000000007",
                SECOND_INVOCATION_UUID,
                INVOCATION_SOURCE,
                CONSUMER_UUID,
                CONSUMER_TARGET,
            ),
        ],
        handles=handles,
    )

    endpoints = {
        (
            edge["source_node_uuid"],
            edge["source_handle_uuid"],
            edge["target_node_uuid"],
            edge["target_handle_uuid"],
        )
        for edge in flattened
    }
    assert endpoints == {
        (PRODUCER_UUID, PRODUCER_SOURCE, INTERNAL_UUID, INTERNAL_TARGET),
        (PRODUCER_UUID, PRODUCER_SOURCE, SECOND_INTERNAL_UUID, INTERNAL_TARGET),
        (INTERNAL_UUID, INTERNAL_READY, SECOND_INTERNAL_UUID, INTERNAL_TARGET),
        (PRODUCER_UUID, PRODUCER_SOURCE, CONSUMER_UUID, CONSUMER_TARGET),
        (SECOND_INTERNAL_UUID, INTERNAL_READY, CONSUMER_UUID, CONSUMER_TARGET),
    }
    assert params == {}


def test_composite_static_passthrough_projects_actual_action_params() -> None:
    """静态组合入参须同时冻结到内部动作和透传输出的下游动作。"""

    nodes = {
        node["uuid"]: node
        for node in (
            _composite_node(static_value=7),
            _node(INTERNAL_UUID, INTERNAL_TEMPLATE),
            _node(CONSUMER_UUID, CONSUMER_TEMPLATE),
        )
    }
    handles = {handle["uuid"]: handle for handle in _handles()}
    flattened, params = ExecutionPlanGraphNormalizer().flatten_composite_edges(
        nodes=nodes,
        edges=[
            _edge(
                "74000000-0000-4000-8000-000000000004",
                INVOCATION_UUID,
                INVOCATION_SOURCE,
                CONSUMER_UUID,
                CONSUMER_TARGET,
            )
        ],
        handles=handles,
    )

    assert params == {
        INTERNAL_UUID: {"value": 7},
        CONSUMER_UUID: {"value": 7},
    }
    assert [
        (edge["source_node_uuid"], edge["target_node_uuid"]) for edge in flattened
    ] == [(INTERNAL_UUID, CONSUMER_UUID)]


@pytest.mark.parametrize("region_type", ["repeat_until", "condition"])
@pytest.mark.parametrize("composite_consumer", [False, True])
def test_completion_inside_control_region_uses_region_barrier(
    region_type: str,
    composite_consumer: bool,
) -> None:
    """组合完成边提升到控制区域后仍可编译，并阻止普通或组合后续动作提前执行。"""

    invocation = _composite_node(static_value=7)
    invocation["parent_uuid"] = REPEAT_REGION_UUID
    internal = _node(INTERNAL_UUID, INTERNAL_TEMPLATE)
    internal["parent_uuid"] = REPEAT_REGION_UUID
    region = _node(REPEAT_REGION_UUID, REPEAT_REGION_UUID, node_type=region_type)
    nodes = {
        node["uuid"]: node
        for node in (invocation, internal, region, _node(CONSUMER_UUID, CONSUMER_TEMPLATE))
    }
    consumer_uuid = CONSUMER_UUID
    consumer_handle = CONSUMER_TARGET
    if composite_consumer:
        nodes[SECOND_INVOCATION_UUID] = _composite_node(
            invocation_uuid=SECOND_INVOCATION_UUID,
            internal_uuid=CONSUMER_UUID,
        )
        nodes[CONSUMER_UUID] = _node(CONSUMER_UUID, INTERNAL_TEMPLATE)
        consumer_uuid = SECOND_INVOCATION_UUID
        consumer_handle = INVOCATION_TARGET
    flattened, _ = ExecutionPlanGraphNormalizer().flatten_composite_edges(
        nodes=nodes,
        edges=[
            _edge(
                "74000000-0000-4000-8000-000000000008",
                INVOCATION_UUID,
                INVOCATION_SOURCE,
                consumer_uuid,
                consumer_handle,
            )
        ],
        handles={handle["uuid"]: handle for handle in _handles()},
    )

    completion_edges = {
        (edge["source_node_uuid"], edge["source_handle_uuid"], edge["target_node_uuid"])
        for edge in flattened
    }
    assert (REPEAT_REGION_UUID, "", CONSUMER_UUID) in completion_edges
    active = {key: nodes[key] for key in (REPEAT_REGION_UUID, CONSUMER_UUID)}
    handles = {handle["uuid"]: handle for handle in _handles()}
    normalizer = ExecutionPlanGraphNormalizer()
    _, runtime_ids = normalizer.runtime_handles(active=active, handles=handles)
    planned = normalizer.contract_edges(
        nodes=nodes,
        active=active,
        edges=flattened,
        handles=handles,
        runtime_handle_ids=runtime_ids,
    )
    assert len(planned) == 1
    assert planned[0]["dependency_only"] is True
    assert planned[0]["source_handle_uuid"] == ""
    assert planned[0]["target_handle_uuid"] == ""
    assert planned[0]["source_data_key"] == ""
    assert planned[0]["target_data_key"] == ""
    assert normalizer.topological_order(active, planned) == [
        REPEAT_REGION_UUID,
        CONSUMER_UUID,
    ]


@pytest.mark.parametrize(
    "source_handle,marked", [("", False), ("missing", False), ("missing", True)]
)
def test_missing_source_handle_is_not_implicitly_a_completion_barrier(
    source_handle: str,
    marked: bool,
) -> None:
    """普通数据边缺失来源连接点时仍拒绝；标记不能掩盖错误的非空连接点。"""

    edge: dict[str, Any] = _edge(
        "edge", PRODUCER_UUID, source_handle, CONSUMER_UUID, CONSUMER_TARGET
    )
    edge["dependency_only"] = marked
    with pytest.raises(ExecutionPlanBuildError, match="工作流边引用快照外连接点"):
        ExecutionPlanGraphNormalizer._direct_edge(
            edge,
            handles={h["uuid"]: h for h in _handles()},
            runtime_handle_ids={(CONSUMER_UUID, CONSUMER_TARGET): "consumer-runtime"},
        )


@pytest.mark.parametrize("target_handle", ["missing", CONSUMER_TARGET])
def test_completion_barrier_still_validates_target(target_handle: str) -> None:
    """纯依赖完成边仍须验证目标连接点存在且属于目标节点。"""

    edge: dict[str, Any] = _edge(
        "edge", REPEAT_REGION_UUID, "", CONSUMER_UUID, target_handle
    )
    edge["dependency_only"] = True
    with pytest.raises(ExecutionPlanBuildError):
        ExecutionPlanGraphNormalizer._direct_edge(
            edge,
            handles={h["uuid"]: h for h in _handles()},
            runtime_handle_ids={},
        )


def test_composite_output_binding_is_frozen_against_internal_job() -> None:
    """父工作流输出引用组合调用时须改写为真实内部 Job，不能保留虚拟节点。"""

    invocation = _composite_node()
    invocation["meta_data"]["unilab"]["composite"]["source_mappings"] = {
        INVOCATION_SOURCE: {
            "kind": "node_output",
            "workflow_node_uuid": INTERNAL_UUID,
            "source_handle_uuid": INTERNAL_READY,
        }
    }
    graph = {
        "workflow": {
            "uuid": WORKFLOW_UUID,
            "revision": 1,
            "name": "composite output",
            "tags": [],
            "meta_data": {
                "unilab": {
                    "input_contract": {"version": 1, "parameters": []},
                    "output_contract": {
                        "version": 1,
                        "outputs": [
                            {"name": "result", "schema": {"type": "integer"}}
                        ],
                    },
                    "output_bindings": {
                        "result": {
                            "kind": "node_output",
                            "workflow_node_uuid": INVOCATION_UUID,
                            "source_handle_uuid": INVOCATION_SOURCE,
                        }
                    },
                }
            },
        },
        "nodes": [invocation, _node(INTERNAL_UUID, INTERNAL_TEMPLATE)],
        "edges": [],
        "node_templates": [
            {
                "uuid": INVOCATION_TEMPLATE,
                "node_type": "workflow",
                "type": "workflow",
            },
            {"uuid": INTERNAL_TEMPLATE, "node_type": "compute", "type": "compute"},
        ],
        "handle_templates": [
            handle
            for handle in _handles()
            if handle["uuid"] in {INVOCATION_SOURCE, INTERNAL_READY}
        ],
    }

    plan, jobs = ExecutionPlanBuilder().build(
        graph, run_mode="normal", target_node_uuid=None
    )
    prepared = prepare_task_input(
        graph=graph,
        raw_input={},
        execution_plan=plan,
        jobs=jobs,
    )

    output_node = next(
        node
        for node in prepared.execution_plan["nodes"]
        if node.get("kind") == "workflow_output"
    )
    assert output_node["output_bindings"]["result"] == {
        "kind": "node_output",
        "workflow_node_uuid": INTERNAL_UUID,
        "source_handle_uuid": INTERNAL_READY,
    }
