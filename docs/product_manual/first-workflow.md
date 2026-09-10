# 手写并运行第一个工作流（用户设备包 教学）

:::{admonition} 阅读角色
- **业务负责人**：确认实验目的、输入输出、参数单位、成功标准和失败处理。
- **开发人员**：编写或编排节点、物料流、控制结构、设备绑定和正式合同。
- **验收人员**：执行静态检查、预检、模拟运行、异常路径和受控真机验收。
:::

本教程使用无硬件副作用的软件探针，创建一个全新的普通工作流。你会亲手完成写源码、导入、诊断、发布、预检、创建 Task 和查看结果。

本页示例假定用户设备包已经提供一个无硬件副作用的软件探针。开发自己的设备包时，先完成[工作区与设备包加载](workspace.md)，再用设备包中已登记的安全测试设备和动作替换示例探针。

日常工作流推荐按[用 AI 编写工作流](ai-workflow-authoring.md)的方式生成；本教程保留手写过程，是为了让你能够读懂、审查和排查 AI 产出的静态 DSL。无论源码由谁写，后面的产品编译、人工发布、预检和运行步骤完全相同。

用户设备包 控制流探针在设备元数据中声明 `hardware_side_effects=False`。本地环境仍应保持[安装教程](installation.md)启动的 `dry-run + develop`，这样即使误选其他动作，也不会构造真机驱动。

## 完成前检查

- Uni-Lab OS 整体状态为 `ready`，且设备连接正常；
- Uni-Lab OS 的“设备”页能找到 `example_lab_control_flow_probe`；
- “工作流”页能看到 用户设备包 已登记流程；
- 当前启动模式为 `develop`，运行模式为 `dry-run`。

如果还没有本地环境，先完成[系统安装](installation.md)。

## 1. 创建源码文件

在任意个人练习目录新建 `hello_probe.py`，保存为 UTF-8，内容如下：

```python
from typing import TypedDict

from example_device_package.devices.control_flow_probe.device import (
    用户设备包ControlFlowProbeDevice,
)
from unilabos.workflow.authoring import device, workflow


class ProbeOutput(TypedDict):
    observed: bool
    message: str


probe: 用户设备包ControlFlowProbeDevice = device("example_lab_control_flow_probe")


@workflow(
    workflow_uuid="683cd317-1767-465c-9483-1664b17a2088",
    displayname="我的第一个软件探针流程",
    description="读取一个布尔值并返回观察结果。",
)
def hello_probe(*, value: bool = True) -> ProbeOutput:
    # unilab:node_uuid=966d4242-af1f-400f-93c9-268927de1451
    observed = probe.observe_boolean(value=value)
    return {
        "observed": observed.value,
        "message": observed.message,
    }
```

:::{important}
这组 UUID 只适合第一次照做。如果当前 Workspace 已导入过本教程，请为工作流和节点生成新的 UUID 字面量。源码里不能写 `uuid.uuid4()`；编译器只接受稳定字符串。
:::

生成两个新 UUID 的辅助命令：

```bash
python -c "from uuid import uuid4; print(uuid4()); print(uuid4())"
```

## 2. 读懂这 27 行代码

1. `TypedDict` 定义可供上层流程和用户读取的输出合同。
2. 设备类型来自真实 用户设备包 驱动包；编译器用它解析动作签名。
3. `device("example_lab_control_flow_probe")` 固定绑定启动图（Graph JSON）中的无硬件副作用设备。
4. `@workflow` 声明稳定身份、展示名和说明；默认类型是 `normal`。
5. `*` 之后的 `value: bool = True` 是公开、带类型、带默认值的输入。
6. 节点 UUID 注释紧邻动作，它是这个节点跨修订保持不变的身份。
7. 动作用命名参数调用并赋值给简单变量。
8. 返回值只引用动作结果，没有伪造常量结果。

不要执行 `python hello_probe.py`。文件是 AST DSL，应该交给 Uni-Lab OS 静态导入。

## 3. 导入工作流

1. 打开 `workspace status` 返回的 Uni-Lab OS 页面地址。
2. 在左侧进入“工作流”。
3. 点击“导入 Python”。
4. 选择 `hello_probe.py`。
5. 等待成功提示，并打开“我的第一个软件探针流程”。

导入只接受单个 `.py` 文件，文件名不能含路径；一个文件必须且只能声明一个有效的工作流 UUID。服务会先验证 UTF-8、Python AST、动作模板、节点身份和完整候选图，全部通过后才原子创建定义并把规范源码登记到 Workspace 包清单。它不会 import 或执行上传文件。

如果失败，先读错误中的行列号和第一个 diagnostic。最常见原因是 UUID 重复、缺节点 UUID、动作参数写成位置参数、设备类型没有显式导入，或动作名不在当前 Catalog。

## 4. 检查定义

在详情中依次确认：

- 类型为普通工作流；
- 当前修订存在，但尚未发布；
- 拓扑只有一个设备动作节点；
- 输入合同包含布尔字段 `value`；
- 输出合同包含 `observed` 和 `message`；
- 诊断没有 error；
- 源码页显示系统保存的规范源码。

如果页面显示模板或设备未绑定，不要继续发布。返回安装检查，确认用户设备包、启动图 与 Uni-Lab OS 设备目录属于同一代 Workspace。

## 5. 发布修订

点击“发布”，确认发布当前修订。发布完成后，页面应显示已发布状态和不可变发布合同。

发布只冻结定义，不是安全审批，也不会启动设备。以后修改源定义会产生新修订；已创建 Task 仍使用自己的旧快照。

## 6. 运行前检查

进入“运行准备”：

1. 输入 `value = true`；
2. 运行方式选择“普通运行”；
3. 优先级选择“普通”；
4. 描述填写“新手教程：hello probe”；
5. 点击“运行前检查”。

结果应为 `runnable_now`。预检不会创建 Task、占用设备或写库存；它只是当前快照上的零写入判断。

如果是 `temporarily_unavailable`，先确认 Uni-Lab OS 中设备已连接且软件探针没有被其他任务占用。如果是 `invalid`，回到诊断、输入与发布状态逐项修复。

## 7. 创建 Task 并查看结果

点击“创建任务”，然后进入“任务”页：

1. 找到描述为“新手教程：hello probe”的任务；
2. 打开任务，观察它从等待/运行进入完成；
3. 点击唯一的 Job；
4. 查看实际输入、`feedback_data`、`return_info` 和输出；
5. 回到 Task 详情核对工作流输出。

在 `dry-run` 中，模拟器会按动作结果合同生成确定性回执：同名输出优先透传输入，所以 `observed` 应与提交的 `value` 相同。字符串 `message` 可以是模拟默认值；它不是 用户设备包 真驱动生成的中文消息。

再创建一次 Task，把 `value` 改为 `false`。如果两次 Task 都完成且 `observed` 分别为 `true`、`false`，你已经验证了：

- Uni-Lab OS 页面与 API 可用；
- Python DSL 能被静态编译；
- 发布合同可运行；
- Uni-Lab OS 能创建并派发 Job；
- 模拟动作能通过 Uni-Lab OS 的正常结果通道回传；
- 工作流输出能从动作结果投影。

## 8. 改用 API 完成同一闭环（可选）

网页是推荐入口；下面的 API 是尚未执行网页导入时的等价入口，不要在已导入同一 UUID 后重复调用。先把 `BACKEND_URL` 改为状态命令返回的 Uni-Lab OS API 地址；如果你已经完成前面的网页教程，请先为工作流和节点换一组新 UUID。

导入：

```bash
curl -fsS -X POST \
  "$BACKEND_URL/api/v1/local/workflows/import-python" \
  -H "Content-Type: text/x-python" \
  -H "X-Workflow-Filename: hello_probe.py" \
  --data-binary @hello_probe.py
```

发布当前修订：

```bash
curl -fsS -X POST \
  "$BACKEND_URL/api/v1/workflows/683cd317-1767-465c-9483-1664b17a2088/publications" \
  -H "Content-Type: application/json" \
  -d '{"revision": 1}'
```

零写入预检：

```bash
curl -fsS -X POST \
  "$BACKEND_URL/api/v1/workflows/683cd317-1767-465c-9483-1664b17a2088/run-preflight" \
  -H "Content-Type: application/json" \
  -d '{
    "run_mode": "normal",
    "target_node_uuid": null,
    "input": {"value": true},
    "inventory_bindings": []
  }'
```

创建 Task：

```bash
curl -fsS -X POST \
  "$BACKEND_URL/api/v1/workflow-tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_uuid": "683cd317-1767-465c-9483-1664b17a2088",
    "run_mode": "normal",
    "priority": "normal",
    "input": {"value": true},
    "inventory_bindings": [],
    "description": "新手教程：hello probe"
  }'
```

接口响应中的 Task UUID 可用于读取 `/api/v1/workflow-tasks/{task_uuid}`、`/jobs` 和 `/events`。

:::{note}
Python 导入是“创建新定义”，不是覆盖已有 UUID。需要长期迭代时，把源码放在设备包的 `workflows/` 目录并登记到 `package.yaml`，或使用 Authoring 的 draft → candidate → apply 并发控制接口。不要反复上传同一个 UUID 期待覆盖。
:::

## 下一课

- 先在[物料管理](materials.md)和[试剂管理](reagents.md)中理解工作流绑定的运行资源；
- 用[工作流编排特性](workflow-features.md)把单动作流程扩展成条件、循环与并行流程；
- 用[实验操作（子工作流）](experiment-operations.md)学习子流程的创建、发布和复用；
- 后续日常创作按[用 AI 编写工作流（推荐）](ai-workflow-authoring.md)完成；
- 上线前完成[运行安全](runtime-safety.md)和[Kubernetes 部署](deployment.md)，再管理工作流和任务。
