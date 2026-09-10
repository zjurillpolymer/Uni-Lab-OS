"""把工作流输出边界收敛到冻结执行计划中的真实来源。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class WorkflowBoundaryBindingError(ValueError):
    """工作流输出绑定无法唯一落到真实执行节点。"""


def flatten_output_bindings(
    *,
    graph_nodes: Sequence[Mapping[str, Any]],
    output_bindings: Mapping[str, Mapping[str, Any]],
    planned_node_uuids: set[str],
) -> dict[str, dict[str, Any]]:
    """把组合调用输出递归改写为执行计划中的叶子节点输出。

    参数：应用图节点、已验证的工作流输出绑定和冻结计划节点身份。返回：不再
    引用虚拟组合调用节点的独立绑定对象。异常：组合元数据缺失、映射成环、
    映射种类不受支持或最终来源不在计划中时抛
    ``WorkflowBoundaryBindingError``；运行时不得猜测来源。
    """

    nodes = {
        str(node.get("uuid") or ""): node
        for node in graph_nodes
        if isinstance(node, Mapping)
    }
    flattened: dict[str, dict[str, Any]] = {}
    for output_name, raw_binding in output_bindings.items():
        binding = dict(raw_binding)
        if binding.get("kind") == "workflow_input":
            flattened[output_name] = binding
            continue
        if binding.get("kind") != "node_output":
            raise WorkflowBoundaryBindingError("工作流输出绑定种类不受支持")
        seen: set[tuple[str, str]] = set()
        while True:
            node_uuid = str(binding.get("workflow_node_uuid") or "")
            handle_uuid = str(binding.get("source_handle_uuid") or "")
            identity = (node_uuid, handle_uuid)
            if not node_uuid or not handle_uuid or identity in seen:
                raise WorkflowBoundaryBindingError("工作流输出绑定身份缺失或成环")
            seen.add(identity)
            if node_uuid in planned_node_uuids:
                flattened[output_name] = binding
                break
            node = nodes.get(node_uuid)
            metadata = node.get("meta_data") if isinstance(node, Mapping) else None
            unilab = (
                metadata.get("unilab") if isinstance(metadata, Mapping) else None
            )
            composite = (
                unilab.get("composite") if isinstance(unilab, Mapping) else None
            )
            mappings = (
                composite.get("source_mappings")
                if isinstance(composite, Mapping)
                else None
            )
            mapped = mappings.get(handle_uuid) if isinstance(mappings, Mapping) else None
            if not isinstance(mapped, Mapping) or mapped.get("kind") != "node_output":
                raise WorkflowBoundaryBindingError(
                    "工作流输出引用的虚拟组合节点没有真实作业来源"
                )
            binding = dict(mapped)
    return flattened


__all__ = ["WorkflowBoundaryBindingError", "flatten_output_bindings"]
