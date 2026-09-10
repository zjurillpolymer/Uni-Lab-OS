# 环境与运行配置

:::{admonition} 阅读角色
- **业务负责人**：确认部署目的、设备包来源、运行环境、安全边界和成功标准。
- **开发或运维人员**：执行安装、配置、启动、升级和故障处理。
- **验收人员**：核对版本、运行状态、失败路径、安全配置和回滚能力。
:::

Uni-Lab OS 的“环境”分为三层：Conda 软件环境决定有哪些 Python/ROS 能力，Workspace 决定加载哪个设备包和设备图，运行配置决定以什么安全模式启动。新手最容易遇到的问题，是把这三层混成一份配置。

## 选择 Conda 环境

Uni-Lab OS 提供三档环境。这里解释它们的用途，不重复安装步骤；首次安装统一按照[系统安装](installation.md)中的版本和命令执行。

| 包 | 适合谁 | 包含什么 | 本手册建议 |
| --- | --- | --- | --- |
| `unilabos` | 只运行已有产品的操作员、部署镜像 | Uni-Lab OS 完整包与核心 ROS 环境 | 普通使用的首选 |
| `unilabos-env` | 需要修改 OS 源码、构建操作页面的开发者 | Python/ROS 环境，不固定 OS 源码 | 本手册源码教程使用 |
| `unilabos-full` | 需要 RViz、Gazebo、MoveIt 或 Jupyter 的仿真开发者 | `unilabos` 加桌面仿真与可视化栈 | 仅按需安装 |

本手册的源码安装路径使用 `unilabos-env`。只有直接运行正式发布包时才选择 `unilabos`；只有确实需要三维仿真或可视化时才选择 `unilabos-full`。环境类型由部署负责人在安装前确认，业务人员不应在安装过程中自行替换。

:::{note}
`--override-channels`、版本号和频道顺序用于保证安装结果一致。升级 Uni-Lab OS 时，应同时确认设备包、启动图（Graph JSON）和环境版本的兼容性，并重新执行验收。
:::

### 环境自检

```bash
python -c "import sys, unilabos; print('python =', sys.executable); print('unilabos =', unilabos.__file__); print('version =', unilabos.__version__)"
python -m pip show unilabos
python -c "import rclpy; print('rclpy: OK')"
python -c "import networkx, yaml, fastapi, uvicorn, multipart; print('核心依赖：OK')"
ros2 interface list | grep unilabos_msgs
ros2 interface show unilabos_msgs/action/StrSingleInput
python -m pip check
```

以第一条命令显示的 Python 解释器和 `unilabos.__file__` 为准，不要根据相邻源码目录、终端提示符或记忆判断当前运行的是哪套 OS。后续的安装、检查、Workspace 启动和测试都应使用同一个 `python`。

`pip show` 中的 `Location` 或 `Editable project location` 应指向预期安装来源，`Version` 应与导入后的 `unilabos.__version__` 一致。两者不一致表示包元数据与源码已漂移，应先重装或重建环境，再继续排查设备包。

接口验收应使用所安装版本实际提供的消息类型，例如 `StrSingleInput`，不要使用已经不存在的类型。

## Workspace 的五个事实输入

以 `user-device-package` 为例，一个可启动 Workspace 至少要能解析以下内容：

| 文件/目录 | 负责什么 | 用户设备包 示例 |
| --- | --- | --- |
| `pyproject.toml` | Python distribution、版本和依赖 | `example_lab-poly-studio` |
| 规范 Python import package | 递归静态扫描 `@device`、`@resource`、动作和模型声明 | `example_device_package/` |
| `package.yaml` | 只登记允许加载的工作流源码和 UUID | 当前登记的 用户设备包 工作流 |
| `deployment/graphs/*.json` | 本次启动的设备实例、资源拓扑与连接参数 | `example_lab-local-debug.json` |
| `deployment/local_config.py` | 本地进程默认配置 | 日志级别、浏览器行为等 |

启动图 是本次激活设备实例和物料拓扑的权威；规范 import package 是设备与资源定义来源；`package.yaml` 只是 Workflow Source 白名单。`devices/`、`resources/` 是推荐的组织目录，不是特殊注册入口，系统会递归静态扫描整个规范 import package。只安装 Python 包但不给 启动图，运行时不会猜测或从远端自动下载设备图。

需要自己建立目录、设备定义、启动图和工作流清单时，按[工作区](workspace.md)完成经过验证的最小闭环。

## Workspace Host 环境文件

Workspace Host 把本地选择保存在：

```text
<workspace>/.unilabos/environment.local.json
```

最小示例：

```json
{
  "schemaVersion": 1,
  "graphPath": "deployment/graphs/example_lab-local-debug.json",
  "externalDevicesOnly": true,
  "runtimeMode": "dry-run",
  "startupMode": "develop",
  "domainMode": "local",
  "backendUrl": null,
  "schedulerUrl": null
}
```

字段含义：

| 字段 | 可选值 | 说明 |
| --- | --- | --- |
| `schemaVersion` | 当前必须为 `1` | Workspace Host 文件格式版本 |
| `graphPath` | Workspace 内相对路径 | 设备/资源图；路径必须留在 Workspace 边界内 |
| `externalDevicesOnly` | `true` / `false` | `true` 时只激活 Workspace 设备包中的外部设备目录 |
| `runtimeMode` | `dry-run` / `normal` | 模拟动作或真实动作；新手固定使用 `dry-run` |
| `startupMode` | `develop` / `product` | 创作可见范围或已发布产品范围 |
| `domainMode` | 只允许 `local` | 当前控制面固定由本机 OS 持有 |
| `backendUrl` | `null` | 历史兼容字段，当前本地控制面不使用 |
| `schedulerUrl` | `null` 或 HTTP(S) URL | 可选的调度地址元数据；普通本地 Workspace 留空 |

第一次学习无需手工创建该文件：`workspace start` 的显式参数会形成启动计划。需要稳定默认值时再保存；命令行传入的 `--graph`、`--runtime-mode` 和 `--startup-mode` 优先用于本次启动。

:::{warning}
不要把旧配置中的 `domainMode: "backend"`、远端 WebSocket bridge 或 `--use_remote_resource` 带入当前产品。代码已经关闭这些常驻远端控制面入口，并会失败关闭。
:::

## 运行模式：先决定是否接触硬件

`runtimeMode` 与 `startupMode` 是两个独立维度：

| 组合 | 定义可见范围 | 动作行为 | 适用场景 |
| --- | --- | --- | --- |
| `dry-run + develop` | 已发布与未发布定义 | 模拟成功回执，不构造真机驱动 | 新手安装、写流程、联调表单 |
| `dry-run + product` | 仅已发布普通工作流 | 模拟成功回执 | 产品视角验收 |
| `normal + develop` | 已发布与未发布定义 | 真实设备动作 | 受控开发环境的真机调试 |
| `normal + product` | 仅已发布普通工作流 | 真实设备动作 | 完成安全验收后的运行环境 |

`develop` 同一时间只接受一个开发任务；`product` 可以让多个已发布任务并行参与调度。切换可见模式不会把不安全工作流变安全，`normal` 也不能替代设备级联锁和现场验收。

PLC-Sim 联调必须让 Driver 真正连接 OPC UA，所以使用 `normal`，同时用专用 启动图 把端点限制在模拟器。具体地址、配置和启动顺序见[PLC-Sim 仿真器](plc-sim.md)。不要仅凭“使用了 PLC-Sim”就把任意 `normal` 启动图 视为安全。

## `local_config.py`

本地模板建议保持最小配置：

```python
class BasicConfig:
    ak = ""
    sk = ""
    disable_browser = True
    no_update_feedback = True
    log_level = "INFO"


class WSConfig:
    reconnect_interval = 5
    max_reconnect_attempts = 999
    ws_ping_interval = 5
    ws_ping_timeout = 8
```

本地控制面不需要 AK/SK，所以示例保持空值。不要把真实凭证写进 Git。`disable_browser=True` 只是不让进程自动拉起浏览器，不会关闭 `/console/`；`no_update_feedback=True` 降低设备反馈刷新；`log_level` 支持 `TRACE`、`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。

当前 Workspace Host 会显式决定进程职责、ROS backend、bridge、端口和 action mode。不要在 `local_config.py` 中与启动计划重复维护这些字段。

## 用环境变量覆盖配置

配置加载器接受统一格式：

```text
UNILABOS_<配置类名>_<字段名>
```

例如：

```bash
export UNILABOS_BASICCONFIG_LOG_LEVEL="DEBUG"
export UNILABOS_BASICCONFIG_FRONTEND_ALLOWED_HOSTS="127.0.0.1,localhost"
export UNILABOS_BASICCONFIG_FRONTEND_SAME_ORIGIN="true"
```

环境变量在 `local_config.py` 之后应用，布尔值接受 `true`、`1` 或 `yes`。包含 `secret`、`token`、`password`、`api_key`、`headers`、`ak` 或 `sk` 的字段会在配置日志中遮蔽，但仍应通过 Secret 管理系统注入，不能写进源码、命令历史或文档。

## Uni-Lab OS 的网络边界

本地教程使用 Workspace Host 返回的 loopback 地址。若要让同一局域网中的浏览器访问，至少配置：

- `frontend_allowed_hosts`：允许的 Host 列表；
- `frontend_same_origin=True`：浏览器访问 `/api/` 时强制同源；
- 可信的反向代理与 TLS；
- 独立的用户认证和授权层。

当前产品没有通用的全局用户登录中间件。不要把本地开发端口直接暴露公网。本手册提供的公网演示入口属于明确授权的测试部署，不能照搬为生产配置。

## 配置完成后的只读核对

```bash
unilab workspace status --workspace "$DEVICE_PACKAGE_ROOT" --json
unilab workspace logs --workspace "$DEVICE_PACKAGE_ROOT" --component backend --json
unilab workspace logs --workspace "$DEVICE_PACKAGE_ROOT" --component edge --json
```

业务人员只需确认 Uni-Lab OS 整体就绪、设备连接正常且工作流加载完整。状态和日志中仍可能出现 `backend`、`edge` 等内部组件字段，供开发人员定位问题；这些字段不代表多个独立产品。单个内部健康检查正常，也不能替代整套系统和设备连接验收。
