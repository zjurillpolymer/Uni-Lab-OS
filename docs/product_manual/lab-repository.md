# 开发一个可加载的实验室仓库

本页带你从空目录建立一个类似 `Uni-Lab-SZLab` 的实验室仓库，并让 Uni-Lab OS 同时加载它的设备定义、设备实例和工作流源码。示例只包含一个无硬件副作用的加热器；完成后，你会得到一条经过当前源码验证的最小闭环。

完成标准是：

- `package inspect` 识别到包命名空间和 1 个设备，并生成 Catalog；
- Registry 导入检查为 `1/1 全部通过`；
- Workspace 的 Backend 与 Edge 都进入 `ready`；
- `workflowProgress` 显示 `loaded: 1, total: 1`；
- Console 能看到“演示：加热样品”，发布后可以用 `dry-run` 创建 Task。

:::{important}
实验室仓库不是一组会被系统任意搜索的 Python 文件。`--workspace` 显式选择唯一仓库；Uni-Lab OS 先把它静态编译为 Package Catalog，再由 Graph 选择本次实例化的设备，由 `package.yaml` 选择允许导入的工作流源码。
:::

## Uni-Lab OS 实际加载什么

```text
pyproject.toml ──► 包身份 / Python 依赖 / 导入包目录
                         │
导入包中的装饰器 ────────┼──► Package Catalog ──► 设备、资源、动作合同
                         │
package.yaml ────────────┴──► 获准的 Workflow 源码

deployment/graphs/*.json ───► 本次设备/资源实例、拓扑、连接参数
                                      │
                                      ▼
                         Backend / Scheduler + Edge Runtime
```

这四层不能互相代替：

| 层 | 权威内容 | 不负责什么 |
| --- | --- | --- |
| `pyproject.toml` | distribution 名称、版本、依赖、构建配置 | 不选择在线设备实例 |
| `@device` / `@resource` | 可用设备、资源和动作定义 | 不声明本次连接地址 |
| `package.yaml` | 明确允许加载的工作流源码及 UUID | 不登记设备/资源定义或实例 |
| Graph | 设备/资源实例、拓扑、`config` 和连接端点 | 不自动发现未声明工作流 |

在本地 Workspace 中，Backend 与 Edge 使用同一个 Package Catalog 和 Graph：Backend/Scheduler 负责编译、任务和调度，Edge 只实例化 Graph 选中的 Driver 并执行 Job。不要把领域仓库写成 Edge 内置调度器。

## 最小目录结构

先创建以下结构。仓库外层名称可以自定；本例的 Python 导入包必须叫 `demo_lab`，并且必须直接位于 Workspace 根目录。

```text
Demo-Lab/
├── pyproject.toml                         # 必需：项目和构建身份
├── package.yaml                           # 本例必需：有 Workflow 时的封闭清单
├── demo_lab/                              # 必需：规范化后的 import package
│   ├── __init__.py
│   ├── devices/
│   │   ├── __init__.py
│   │   └── demo_heater/
│   │       ├── __init__.py
│   │       └── device.py                  # @device / @action
│   └── workflows/
│       ├── __init__.py
│       └── heat_sample.py                 # @workflow
└── deployment/
    ├── local_config.py                    # Workspace Host 当前要求此路径
    └── graphs/
        └── local.json                     # 本次激活的物理图
```

:::{warning}
当前 Workspace 只接受根目录下的扁平 import package，即 `<workspace>/demo_lab/__init__.py`。`<workspace>/src/demo_lab/` 不在当前扫描和导入合同内，会被判定为缺少规范 Python 包；不要同时维护 flat 与 `src/` 两套布局。
:::

面向长期维护的仓库可按需要扩展为：

```text
Demo-Lab/
├── README.md                            # 安装、启动、联锁和恢复入口
├── .gitignore
├── .github/workflows/check_registry.yml # 无硬件 CI
├── pyproject.toml
├── package.yaml
├── demo_lab/
│   ├── __init__.py
│   ├── common/                          # 共享协议、日志、网关
│   ├── config/
│   │   └── address_tables/              # 现场批准的 CSV/JSON/YAML 地址表
│   ├── resources/                       # @resource、仓库和 Site 定义
│   ├── devices/<id>/
│   │   ├── device.py                    # 公开 Device/Action 合同
│   │   ├── transport.py                 # Serial/HTTP/OPC UA 适配
│   │   ├── simulator.py                 # 可选的同合同模拟实现
│   │   └── assets/                      # 设备本地表和模型
│   ├── workflows/                       # 叶子与组合工作流
│   └── assets/                          # 公共图标和二维/三维模型
├── deployment/graphs/                   # 各环境的实例与端点
├── tests/                               # Catalog、Action、资源、工作流和模拟器
├── scripts/                             # inspect、build、启动和部署脚本
└── docs/                                # 协议、联锁、恢复和验收记录
```

只创建本次切片真正需要的目录，不要用空目录模拟完成度。只有启动器或 CI 确实读取 `requirements.txt` 时才保留它，并避免与 `pyproject.toml` 重复声明不同版本的依赖。

`devices/`、`resources/` 是 SZLab 推荐的领域组织方式，不是魔法注册目录。Package Catalog 会递归静态扫描规范 import package 中的 `.py`；工作流源码还必须进入 `package.yaml` 白名单。

## 1. 固定包身份

先写 `pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "demo-lab"
version = "0.1.0"
description = "Minimal Uni-Lab OS laboratory workspace"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
runtime = ["unilabos"]
dev = ["build>=1.2", "pytest>=8", "ruff>=0.6"]

[tool.setuptools.packages.find]
include = ["demo_lab*"]

[tool.unilabos.startup]
graph = "deployment/graphs/local.json"
config = "deployment/local_config.py"
ensure_dependencies = true
```

最小示例没有额外资产。加入 CSV、YAML、图片、Xacro 或 mesh 后，还要让它们进入 wheel；否则 editable 模式可能正常，部署包却缺文件：

```toml
[tool.setuptools.package-data]
demo_lab = [
  "**/*.csv", "**/*.json", "**/*.yaml", "**/*.yml",
  "**/*.xacro", "**/*.urdf", "**/*.stl", "**/*.glb",
  "**/*.png", "**/*.jpg", "**/*.jpeg",
]
```

`project.name` 会把连字符、点和下划线规范化成小写下划线形式。这个结果决定后续所有身份：

| 名称用途 | 本例的值 |
| --- | --- |
| distribution | `demo-lab` |
| Python 导入包目录 | `demo_lab/` |
| `package.yaml` 包名 | `demo_lab` |
| 社区命名空间 | `community.demo_lab` |
| 设备定义全名 | `community.demo_lab.demo_heater` |

以上身份必须一致。不要手工发明另一套 namespace，也不要保留类似旧 Profile 的第二套设备发现配置。

`runtime` 只声明该仓库需要 Uni-Lab OS，不替代部署环境的版本锁。先按[环境与运行配置](environment.md)确认实际解释器、源码位置和版本，再让环境锁文件或镜像选择经过验证的 OS 版本。

`[tool.unilabos.startup]` 是可选的包自描述元数据。首次启动仍应显式给出 Workspace 和 Graph；不要在领域包中固定 `app_bridges`。真实 Driver 的第三方库应写入 `dependencies` 并固定兼容范围，凭证不得写进项目文件或 Git。

## 2. 声明允许加载的工作流

创建 `package.yaml`：

```yaml
package:
  name: demo_lab

workflows:
  - workflow_uuid: 5c98f0ac-828e-4af7-906b-86a14c1198bc
    source: demo_lab/workflows/heat_sample.py
```

这里使用封闭清单：顶层只能有 `package` 和 `workflows`；每项只能有 `workflow_uuid` 和 `source`。路径必须是以下两种三段式路径之一：

- `<package>/workflows/<file>.py`：普通工作流；
- `<package>/experiment_operations/<file>.py`：可复用实验操作。

同一个 UUID 还必须原样写在源码的 `@workflow` 中。没有列在清单里的 `.py` 不会因为位于 `workflows/` 就被自动加载。新仓库尚无工作流时可以显式写 `workflows: []`，不能写 `null` 或省略字段。

生成新 UUID：

```bash
python -c "import uuid; print(uuid.uuid4())"
```

## 3. 定义设备和动作

创建 `demo_lab/devices/demo_heater/device.py`：

```python
from __future__ import annotations

from typing import TypedDict

from unilabos.registry.decorators import action, device, topic_config


class SetTemperatureResult(TypedDict):
    success: bool
    message: str
    actual_temperature: float


@device(
    id="demo_heater",
    displayname="演示加热器",
    category=["heater"],
    description="用于学习实验室仓库加载方式的无硬件设备",
    metadata={"transport": "in_process", "hardware_side_effects": False},
)
class DemoHeater:
    def __init__(
        self,
        endpoint: str = "sim://local",
        initial_temperature: float = 25.0,
    ) -> None:
        self.endpoint = endpoint
        self._temperature = float(initial_temperature)
        self._status = "Idle"

    @property
    @topic_config()
    def status(self) -> str:
        return self._status

    @action(
        displayname="设置温度",
        description="在演示驱动中更新温度并返回结构化结果",
    )
    def set_temperature(
        self,
        target_temperature: float,
        duration_seconds: float = 1.0,
    ) -> SetTemperatureResult:
        """设置目标温度。

        Args:
            target_temperature[目标温度]: 摄氏温度，范围为 0 到 200。
            duration_seconds[持续时间]: 模拟持续时间，单位为秒。
        """
        if not 0.0 <= target_temperature <= 200.0:
            raise ValueError("target_temperature 必须在 0 到 200 之间")
        if duration_seconds < 0.0:
            raise ValueError("duration_seconds 不能小于 0")
        self._status = "Running"
        self._temperature = float(target_temperature)
        self._status = "Idle"
        return {
            "success": True,
            "message": f"温度已设置为 {self._temperature} °C",
            "actual_temperature": self._temperature,
        }
```

这段代码体现了最小 Driver 合同：

- `@device.id` 只允许英文、数字和下划线；`category` 必填；
- Uni-Lab OS 会静态读取 `@device`、`@action`、类型注解和文档，不靠导入 `__init__.py` 触发注册；
- 装饰器必须用官方名称直接导入和调用；不要改成别名，也不要写成 `decorators.device(...)`，否则静态扫描可能无法识别；
- Graph 的 `config` 会作为构造参数传给 Driver，字段名必须与 `__init__` 的显式命名参数对齐；
- 不要用一个通用 `config` 字典或 `**kwargs` 吞掉未知字段；显式参数让 Graph 与构造合同便于审查，并让拼写错误在 Driver 构造时尽早失败；
- `@action` 参数和具名结果会形成 Console 表单、Job 参数和结果 Schema；
- 状态属性使用 `@topic_config()`，不应把只读辅助方法误暴露为动作；
- 所有给用户调用的公开方法都显式加 `@action()`；公共辅助方法优先以下划线开头，必须公开时用 `@not_action`；
- 返回值应可 JSON 序列化，并明确表达成功、失败和业务结果。

真正的设备 Driver 还必须实现有限超时、连接/断连、设备忙与未知结果处理、日志脱敏和幂等策略。不要在 import 或装饰器求值阶段连接硬件；只允许 Graph 选中的 Driver 在运行激活阶段建立连接。

Action 的具名结果可使用普通 `TypedDict` 或受支持的 frozen dataclass。Workflow 若声明具名结果类型，只接受一个普通 `TypedDict`；也可不声明结果记录并使用 `workflow_output(...)`，但不能把 Action 的 dataclass 写法直接复制过来。

## 4. 用 Graph 建立设备实例

创建 `deployment/graphs/local.json`：

```json
{
  "nodes": [
    {
      "id": "heater_1",
      "uuid": "ba47b429-8584-4aa4-aeb9-663c099c8e32",
      "name": "演示加热器 1",
      "parent": null,
      "type": "device",
      "class": "community.demo_lab.demo_heater",
      "position": {"x": 0, "y": 0, "z": 0},
      "config": {
        "endpoint": "sim://local",
        "initial_temperature": 25.0
      },
      "data": {"status": "Idle"}
    }
  ],
  "links": []
}
```

三个容易混淆的 ID 在这里汇合：

| 字段 | 含义 | 本例 |
| --- | --- | --- |
| `@device(id=...)` | 设备类型的包内 ID | `demo_heater` |
| Graph `class` | 设备类型的规范全名 | `community.demo_lab.demo_heater` |
| Graph `id` | 当前实验室中的设备实例 ID | `heater_1` |

`class` 推荐始终使用 Package Catalog 输出的规范 FQID；代码仅为兼容接受“全 Catalog 唯一”的短 ID，发生歧义就会失败，不应把它作为新仓库写法。`id` 必须在当前 Graph 中稳定且唯一。工作流固定绑定的是实例 `id`。Graph 同时是设备连接参数和资源拓扑的权威，不要在 Driver、Workflow 和部署脚本中各维护一份不同地址。

真实设备的密码或 token 不应进入 Graph。通过环境变量或部署 Secret 注入，并让构造器只接收引用或非敏感连接参数。

## 5. 编写第一个工作流

创建 `demo_lab/workflows/heat_sample.py`：

```python
from __future__ import annotations

from typing import TypedDict

from demo_lab.devices.demo_heater.device import DemoHeater
from unilabos.workflow.authoring import device, workflow


class HeatSampleOutput(TypedDict):
    final_temperature: float


heater: DemoHeater = device("heater_1")


@workflow(
    workflow_uuid="5c98f0ac-828e-4af7-906b-86a14c1198bc",
    displayname="演示：加热样品",
    description="调用一个演示设备动作，验证实验室仓库加载闭环。",
)
def heat_sample(
    *,
    target_temperature: float = 60.0,
    duration_seconds: float = 1.0,
) -> HeatSampleOutput:
    # unilab:node_uuid=7bc49d5a-a202-47e6-b0d5-e8a84b7520ca
    heated = heater.set_temperature(
        target_temperature=target_temperature,
        duration_seconds=duration_seconds,
    )
    return {"final_temperature": heated.actual_temperature}
```

关键对应关系是：

```text
DemoHeater 类型注解 ──► 验证动作是否存在、参数和结果是否匹配
device("heater_1") ────► 固定绑定 Graph 实例
@workflow UUID ─────────► 必须匹配 package.yaml
node_uuid 注释 ─────────► 节点跨保存、画布和修订的稳定身份
```

工作流是静态 DSL，不要运行 `python demo_lab/workflows/heat_sample.py`。每个源文件只能有一个 Workflow 函数；模块级只放允许的 docstring、绝对 import、带类型的设备选择器、可选结果 `TypedDict` 和该函数。

所有公开输入都必须是带类型的 keyword-only 参数，不能有普通位置参数、`*args` 或 `**kwargs`。动作调用必须赋给简单变量并只使用命名参数；各节点前都需要紧邻的唯一节点 UUID。

需要正式结果记录时，Workflow 只能声明一个普通 `TypedDict` 并返回匹配字段的字典；也可以不声明结果记录，改用 `workflow_output(...)`。它与前一节允许 frozen dataclass 的 Action 结果合同不同。完整限制见[先理解工作流](workflow-concepts.md)和[工作流编排特性](workflow-features.md)。

## 6. 提供 Workspace 本地配置

创建 `deployment/local_config.py`：

```python
class BasicConfig:
    ak = ""
    sk = ""
    disable_browser = True
    no_update_feedback = True
    log_level = "INFO"
```

Workspace Host 当前固定读取这个路径。`ak`、`sk` 在本地控制面保持空值；任何真实凭证都应由 Secret 管理系统或环境变量注入。

## 7. 按四道门验证仓库

在已经完成[安装并启动本地产品](installation.md)的 Python 3.11 环境中执行：

```bash
LAB_ROOT="/absolute/path/to/labs"
cd "$LAB_ROOT/Demo-Lab"
python -m pip install -e '.[dev]'
python -m pip check
```

这是新仓库的默认安装方式：它会安装领域运行依赖和测试工具，并验证 editable packaging。只有镜像或 Conda 环境已经用同一份锁文件提供全部依赖时，才可使用 `--no-deps`；使用后仍必须执行 `pip check`。

Workspace 会把仓库根加入自己的 `PYTHONPATH`，因此 editable install 不是第二套设备发现机制。它用于验证 Python packaging，运行时仍只扫描 Workspace 根下的规范 import package。

### 门 1：静态编译完整 Catalog

```bash
unilab package inspect \
  --path "$LAB_ROOT/Demo-Lab" \
  --out "$LAB_ROOT/Demo-Lab/dist/inspect"
```

应看到：

```text
class_namespace : community.demo_lab
设备数          : 1 (demo_heater)
```

这个步骤会受限地静态编译 Catalog，并写出归档和检查产物，不执行作者 Driver。它可发现编译器覆盖的语法、身份、装饰器和清单问题，但输出摘要不等于 Registry 导入、Driver 构造、工作流运行或真机验收。

### 门 2：验证 Registry 能导入类型

```bash
CHECK_DIR="$(mktemp -d)"

if CHECK_OUTPUT="$(unilab \
  --check_mode \
  --workspace "$LAB_ROOT/Demo-Lab" \
  --graph deployment/graphs/local.json \
  --config "$LAB_ROOT/Demo-Lab/deployment/local_config.py" \
  --external_devices_only \
  --working_dir "$CHECK_DIR" 2>&1)"; then
  CHECK_STATUS=0
else
  CHECK_STATUS=$?
fi

printf '%s\n' "$CHECK_OUTPUT"
if (( CHECK_STATUS != 0 )) || grep -Eq '\[ERROR\]|[0-9]+ 个错误' <<<"$CHECK_OUTPUT"; then
  echo "Registry 导入检查失败" >&2
  exit 1
fi
```

应看到 `验证完成: 1/1 全部通过`。当前底层 `--check_mode` 即使输出导入错误也可能返回退出码 0，因此 CI 必须像上例一样同时检查退出码和 `[ERROR]` / `N 个错误`；只检查 `$?` 会产生假通过。这一步证明类型可以解析和导入，但仍不代表真机连接、构造器、联锁或动作已经通过运行验收。

### 门 3：构建并自审计 wheel

```bash
unilab package build \
  --path "$LAB_ROOT/Demo-Lab" \
  --out "$LAB_ROOT/Demo-Lab/dist/build"
```

成功时会生成 wheel、`package.catalog.json` 及摘要。构建器会从 wheel 重建并再次编译 Catalog，避免出现“源码目录可用、发布包缺文件”的情况。

### 门 4：用安全模式真正加载 Workspace

```bash
unilab workspace start \
  --workspace "$LAB_ROOT/Demo-Lab" \
  --graph deployment/graphs/local.json \
  --runtime-mode dry-run \
  --startup-mode develop \
  --wait 300 \
  --json
```

成功结果至少包含：

- `components.backend.phase = ready`；
- `components.edge.phase = ready`；
- `packageMounts.items[0].namespace = community.demo_lab`；
- `workflowRuntimePhase = ready`；
- `workflowProgress.loaded = 1` 且 `total = 1`。

再查看状态和日志：

```bash
unilab workspace status \
  --workspace "$LAB_ROOT/Demo-Lab" \
  --json

unilab workspace logs \
  --workspace "$LAB_ROOT/Demo-Lab" \
  --component backend \
  --json

unilab workspace logs \
  --workspace "$LAB_ROOT/Demo-Lab" \
  --component edge \
  --json
```

从状态结果取得 Backend 的 loopback `address`，在后面加 `/console/` 打开 Console。进入“工作流”，找到“演示：加热样品”，检查并发布当前修订，执行零写入预检后再创建 Task。界面操作可参考[SZLab 手写教程](first-workflow.md)，但设备类和实例应使用本仓库定义。

结束时统一停止：

```bash
unilab workspace stop \
  --workspace "$LAB_ROOT/Demo-Lab" \
  --wait 300 \
  --json
```

:::{warning}
`dry-run` 不构造真实 Driver，而是模拟动作回执。它证明仓库发现、Catalog、Graph、工作流、Backend、Edge 和 Scheduler 链路可以装载，不能证明真实设备代码可用。只有把 Graph 的全部端点限制在隔离模拟器或获准测试设备，并完成现场安全检查后，才可用 `normal` 验证 Driver 构造和通信。
:::

### 可选门 5：验证无硬件 Driver 的真实激活

本页的 `DemoHeater` 已明确标记为无硬件副作用，`endpoint` 也是 `sim://local`。停止 dry-run Workspace 后，可以只对这个示例执行一次：

```bash
unilab workspace start \
  --workspace "$LAB_ROOT/Demo-Lab" \
  --graph deployment/graphs/local.json \
  --runtime-mode normal \
  --startup-mode develop \
  --wait 300 \
  --json
```

随后在 `/api/v1/online-devices` 或 Console 中确认 `heater_1` 在线，再运行已发布的示例工作流。这样才覆盖 Driver import、构造器和真实 action 调用。完成后立即执行 `workspace stop`。

不要把这一步直接套到物理设备 Graph。对于 PLC、机械臂、泵、相机等 Driver，必须先改用隔离模拟器，或完成现场连接、联锁、急停、物料、超时与未知结果恢复验收。

### 面向长期维护的 CI 与验收

把前四道门放进 `.github/workflows/check_registry.yml`，并从干净 checkout 开始。CI 至少执行 editable 安装、`pip check`、`package inspect`、上面的现代 `--workspace` Registry 检查和 `pytest -q`，且继续检查 Registry 输出中的错误文本。

测试应覆盖以下分层合同：

- 比较生成的 Device、Action、Resource 和 Site Schema，防止字段、单位或稳定 ID 漂移；
- 验证工作流执行 Python → graph → 规范化 Python → graph 后语义固定，不只比较格式；
- 从空状态加载组合工作流，证明子工作流先于父工作流解析，反复扫描最终达到同一固定点；
- 让模拟器执行代表性 Action、最短叶子工作流和关键故障注入；普通 CI 不连接实验室硬件；
- 在 Theia Workbench 验收选择 Workspace、启动 OS、编辑/保存、发布、预检、运行、停止、日志和图状态。

物理验收必须独立记录 Graph、地址表和固件版本，以及连接、联锁、急停、超时、取消和未知结果恢复的现场见证。模拟器、dry-run 或 Workbench 界面通过，都不能替代这份证据。

## 从最小仓库扩展到 SZLab 规模

通过上述闭环后，再按垂直切片扩展，而不是一次加入所有设备：

1. 每次增加一个 `@device` 类型、一个 Graph 实例和一个最小动作工作流。
2. 把通信、超时、重连和协议字段放入 `common/` 或设备目录，不放进 Workflow。
3. 用 `@resource` 定义容器、耗材、仓库和 Deck；Graph 中由每个子节点的 `parent`（或 `parent_uuid`）和稳定 `id` 建立实例拓扑。输入 JSON 的 `children` 只是兼容字段，不能依赖它反向创建父子关系。
4. 模型资产放在定义所属目录的 `models/`，`model.entry` 相对装饰器所在文件解析；同时在 setuptools package data 中包含资产扩展名。
5. 复杂工艺拆为普通 Workflow 与 `experiment_operations/` 中的可复用操作；每个源码都登记在 `package.yaml`。
6. 为 Driver 参数校验、动作结果、工作流编译、Graph 引用、仿真行为和故障恢复增加测试。
7. 每次变更都重复 inspect → Registry check → build → dry-run；设备装饰器或 Graph 变化后重启 Workspace，再观察新代次。

SZLab 的职责拆分可以作为参考：

| 目录 | SZLab 中的用途 | 你的仓库中建议放什么 |
| --- | --- | --- |
| `devices/` | PLC、机器人、S04–S09 Driver 与动作 | 设备协议和最小动作原语 |
| `common/` | PLC gateway、动作日志、站点映射 | 多设备共享、但不属于调度器的基础能力 |
| `resources/` | 物料、容器、仓库、Deck | 实验室资源模板和库位定义 |
| `workflows/` | 普通实验流程与控制流示例 | 组合动作的静态 DSL |
| `deployment/graphs/` | 真机、PLC-Sim 和不同部署图 | 每套环境唯一、可审计的实例与端点 |
| `tests/` | Driver、Workflow、Graph、物料与 E2E | 从静态合同到模拟器的分层验收 |

不要把 SZLab 当前的设备数量、工作流数量或 NodeId 原样复制到新实验室。复制它的目录合同和验证方式，再以目标设备协议为事实建立自己的定义。

### 像 SZLab 一样共享 PLC 连接

如果多个业务工站由同一台 PLC 控制，推荐复用 SZLab 的网关模式，而不是让每个 Driver 重复连接 OPC UA：

```text
业务设备 A ─┐
业务设备 B ─┼─ plc_device_id ─► 唯一 PLC Driver 实例 ─► OPC UA / PLC-Sim
业务设备 C ─┘
```

Graph 中只有 PLC 节点保存 `url`、节点表路径和自动连接选项；业务设备只保存 `plc_device_id`，在激活阶段取得共享网关。这样能集中处理会话、重连、NodeId 映射、日志和故障状态。它是 SZLab 的推荐工程模式，不是所有领域仓库的加载硬要求。开发期应同时准备 PLC-Sim Graph，具体入口和连接方式见 [PLC-Sim 使用指南](plc-sim.md)。

涉及器皿、耗材、库位或物料流时，再增加 `@resource` 模板；实际资源实例、父子关系和挂载位置仍由 Graph 给出。动作之间用带 `AllowedResourceTemplates` 的 `ResourceSlot` 传递物料，不要只传字符串 ID。详见[资源、物料与库存](materials.md)。

### 让真实设备与模拟器保持同一合同

真实实现和模拟实现可以使用不同 transport，但面向 Registry 和 Workflow 的公开合同必须一致：Action 名称、参数类型与默认值、具名结果 Schema、状态 topic 名称和含义都不能漂移。同一工作流与 Workbench 表单应能复用，不需要改写设备动作符号。

模拟器应提供确定性的状态推进、时延以及可控的超时和故障注入，且不得调用真实传输。`dry-run` 只是模拟动作回执，不会构造模拟 Driver；需要验证 Driver 或协议时，应在隔离 Graph 中用 `normal` 连接对应模拟器。

使用当前 OS 已实现的 Graph、构造参数或领域内 transport 选择方式。现行公共合同没有通用的 `device_pair.yaml` 或 `--sim_engine` 入口，不要根据规划文档自行创建这些文件或参数。

## 部署时怎样让 Backend 和 Edge 都能加载

本地开发由 Workspace Host 给两个子进程加入同一个仓库根。容器或 Kubernetes 部署则必须显式交付相同内容：

- 镜像或挂载内必须包含可被 `--workspace` 指向的源码工作区：`pyproject.toml`、规范 import package、`package.yaml` 和 `deployment/`。经过 `package build` 自审计的 wheel 是发布产物与交付证据，但当前不能单独代替主 Workspace 的源码目录；
- Backend 与 Edge 使用相同的包版本、Catalog digest 和 Graph 内容；
- 两个进程都以同一个 `--workspace` 合同启动；
- Graph 中的连接端点按容器网络改写，不能继续使用开发机的 `127.0.0.1`；
- Driver 依赖同时存在于 Edge 运行环境；只有 Graph 选中的 Driver 会在 Edge 激活；
- 密钥通过 Kubernetes Secret 注入，Graph 和镜像不保存明文凭证。

SZLab 当前部署镜像就是把 OS 源码以及 SZLab 的 `pyproject.toml`、`package.yaml`、`szlab_poly_studio/` 和 `deployment/` 固定到同一个版本，再让 Backend 与 Edge 指向同一 Workspace 和 Graph。部署成功的判据不是 Pod 仅仅为 Running，而是 Catalog 代次一致、Backend/Edge Ready、设备在线且工作流预检通过。

## 推荐让 AI 编写后续工作流

当第一个设备切片已经通过四道门后，后续 Workflow 推荐交给 AI 起草。给 AI 的输入必须来自当前仓库，而不是只给自然语言设备名称：

```text
请以当前 Uni-Lab OS 和本实验室仓库源码为唯一事实依据：
1. 先读取 pyproject.toml、package.yaml、目标 Graph；
2. 扫描 Graph 中实际实例化的 class/id，以及对应 @device/@action 的参数和结果类型；
3. 找到 Uni-Lab-SZLab 中结构最相近的工作流，仅借鉴写法，不复制设备 ID；
4. 使用 unilabos.workflow.authoring 静态 DSL，保留明确的 @workflow UUID；
5. 为每个动作、物料来源、条件、循环、分组或子工作流调用生成稳定且唯一的 node_uuid；
6. 只使用命名参数，不发明设备、动作、结果字段、资源或 API；
7. 同步更新 package.yaml，并先运行 package inspect 和 dry-run 验证；
8. 不切换 normal，不连接真机，不发布或运行，直到我人工审查。

目标：<描述实验目标、输入、输出和失败条件>
```

AI 生成后，人必须核对 Graph 端点、设备实例、动作参数单位、资源锁、物料来源、超时、失败和恢复语义。详细流程见[用 AI 编写工作流（推荐）](ai-workflow-authoring.md)。

## 常见加载失败

| 现象 | 代码合同中的常见原因 | 修复 |
| --- | --- | --- |
| 缺少规范 Python 包 | 包放在 `src/`、规范名与目录不同，或缺少 `__init__.py` | 把规范 import package 直接放在 Workspace 根，并统一身份 |
| `invalid_manifest` | `package.yaml` 多字段、缺字段、`workflows: null`、重复键或路径越界 | 使用本页的封闭结构；空包写 `workflows: []` |
| 工作流没有出现 | 源码未列入 `package.yaml`，或 UUID 与装饰器不一致 | 同步清单、路径和 UUID，然后重启/重新加载 |
| `python_syntax_error` | import package 内任一 Python 文件语法损坏 | 修复全部诊断；系统不会发布部分 Catalog |
| 设备定义找不到 | Graph `class` 无法解析，或使用了有歧义的兼容短 ID | 从 inspect 输出复制 `community.<package>.<device_id>` 规范 FQID |
| 工作流绑定不到设备 | `device("...")` 与 Graph 实例 `id` 不一致 | 绑定实例 ID，而不是 `@device` 类型 ID |
| Driver 导入失败 | 依赖未装、绝对 import 错误或类已移动 | 在同一环境安装依赖并运行 Registry check |
| dry-run 成功但 normal 失败 | dry-run 没有构造 Driver | 在隔离模拟器中检查构造器、连接、超时和动作 |
| 本地可用、容器不可用 | 镜像漏掉包文件/资产/依赖，或容器仍使用本机地址 | 自审计 wheel；核对镜像内容、Catalog digest 与网络端点 |

此外，工作区不接受越过仓库边界或通过符号链接偷渡的 Graph、配置、Python 来源。现代 Package Catalog 会递归收集整个规范 import package；其中任意一个 `.py` 的编码或语法错误都会让整包原子失败。保持一个清晰的 import package，不要把虚拟环境、构建产物或第三方源码塞进包目录。

## 提交前清单

- [ ] `project.name`、import package、`package.yaml` 和 `community.*` 身份一致；
- [ ] 所有设备/资源 ID 唯一，Graph `class` 来自 inspect 结果；
- [ ] 每个 Workflow UUID 与 `package.yaml` 完全一致；
- [ ] Graph 实例 ID 稳定，Workflow 绑定的是实例而不是类型；
- [ ] Driver 依赖已声明，凭证未进入源码、Graph 或日志；
- [ ] `package inspect`、Registry check 和 `package build` 全部通过；
- [ ] Action Schema 与真实/模拟合同一致，工作流 round-trip 达到语义固定点；
- [ ] 组合工作流从空状态按 child-first 固定点完整加载；
- [ ] `dry-run + develop` 下 Backend/Edge Ready，工作流全部 loaded；
- [ ] Workbench 的编辑、保存、发布、预检、运行和停止链路已验收；
- [ ] 切换 `normal` 前另做隔离模拟器或真机安全验收；
- [ ] 容器中的 Backend/Edge 使用同一包、Catalog 和 Graph 代次。

<div class="evidence">
<strong>实现依据与实测</strong>
<p><code>workspace_runtime/discovery.py</code>（根目录 flat package 与边界）；<code>package_catalog/project_metadata.py</code> 和 Python compiler（项目身份与静态 Catalog）；<code>workflow/source_manifest.py</code>（封闭清单）。</p>
<p><code>registry/{decorators,ast_registry_scanner,registry}.py</code>（Device、Resource 与 Action）；<code>workflow/authoring_ast.py</code>、<code>authoring_engine.py</code> 和 <code>service.py</code>（DSL、round-trip 与 child-first 固定点）。</p>
<p><code>resources/graphio.py</code>、<code>package_manager/driver_runtime/</code> 和 <code>workspace_host/{cli,launch}.py</code>（Graph、Driver 激活与双进程）；SZLab 仓库用于实例对照。</p>
<p>本页最小样例已在当前源码通过 inspect、Registry 1/1、wheel 自审计、dry-run 启停和无硬件 Driver 的 normal 激活；Backend/Edge Ready，工作流加载 1/1，<code>heater_1</code> 已上线。</p>
</div>
