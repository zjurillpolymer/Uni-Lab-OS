# 工作区

:::{admonition} 阅读角色
- **业务负责人**：确认设备包范围、现场对象、业务名称和交付目标。
- **开发人员**：建立目录、登记清单、依赖、启动图和测试。
- **验收人员**：确认设备包能够被检查、构建、模拟启动并留下版本记录。
:::

工作区是用户设备包的项目根目录。它把设备类型、物料模板、启动图（Graph JSON）、工作流和测试放在同一个可交付版本中，供 Uni-Lab OS 检查和加载。

设备包由用户自行准备。Uni-Lab OS 不会从任意目录猜测要加载哪些文件；启动时必须通过 `--workspace` 指向一个明确的设备包根目录。

(workspace-initialization)=
## 初始化工作区

安装 Uni-Lab OS 后，可以用 `unilab workspace init` 创建一个设备包工作区。命令生成 15 个文件，包含一个无硬件副作用的示例设备、一个 `echo` 动作和一个调用该动作的普通工作流。

### 创建命令

在已经安装 Uni-Lab OS 的 Python 环境中运行：

```bash
unilab workspace init --help
```

若提示没有 `init` 子命令，当前安装的版本尚未包含此功能，需要更新到包含该功能的版本；也可以先使用[已准备好的示例设备包](demo-lab.md)。命令可用后创建工作区：

```bash
unilab workspace init --output ./sample-lab
```

目标目录必须尚不存在，已有空目录也会被拒绝。命令只生成文件；依赖安装、设备包检查和工作区启动由后续命令完成。

默认使用输出目录名派生包身份：`sample-lab` 对应发布名称 `sample-lab`、Python 包目录 `sample_lab/` 和类型命名空间 `community.sample_lab`。需要单独指定名称或供脚本读取时：

```bash
unilab workspace init --output ./device-workspace --name sample_lab --json
```

`--name` 以小写英文字母开头，以字母或数字结尾，中间可以使用小写字母、数字、点、连字符和下划线。连续分隔符统一折叠为一个下划线；规范化后不能是 `class`、`import` 等 Python 关键字。省略 `--name` 时，目录名先转为小写再按相同规则检查。

`--json` 返回工作区绝对路径、发布名称、Python 包名、创建的文件清单和下一步命令。非法名称、目标已存在或写入失败时，命令以非零状态退出并返回错误码；不会覆盖已有目录。

### 生成内容

```text
sample-lab/
├── .gitignore
├── DEVICE_PACKAGE_REQUIREMENTS.md
├── README.md
├── pyproject.toml
├── package.yaml
├── deployment/
│   ├── local_config.py
│   └── graphs/
│       └── dry-run.json
├── sample_lab/
│   ├── __init__.py
│   ├── devices/
│   │   ├── __init__.py
│   │   └── demo_device.py
│   ├── resources/
│   │   └── __init__.py
│   ├── experiment_operations/
│   │   └── __init__.py
│   └── workflows/
│       ├── __init__.py
│       └── demo_workflow.py
└── tests/
    └── test_workspace_contract.py
```

- `pyproject.toml`：一致的包身份、构建配置、开发依赖以及默认启动图和配置文件。
- `package.yaml`：登记示例工作流的源文件和 UUID，与源码装饰器保持一致。
- `demo_device.py`：定义 `DemoDevice.echo(text)`，返回 `success` 和 `echoed_text`。
- `demo_workflow.py`：调用 `demo_device_01` 的 `echo` 动作并返回结果。
- `dry-run.json`：包含一个示例设备实例，其 `class` 与生成的设备类型一致。
- `local_config.py`：关闭自动打开浏览器和更新反馈，设置 INFO 日志级别。
- 需求卡、README 和测试：记录待确认的业务事实，并验证包身份、启动文件、目录发现和回显动作。

`resources/` 和 `experiment_operations/` 当前只有 `__init__.py`，分别预留给物料模板和可复用实验操作。初始化没有生成物料类型、PLC 协议适配、PLC-Sim 配置或生产图。按下文规范补充实际需要的内容；`common/` 等共享代码目录按需创建。

### 验证和继续开发

先进入生成的目录并执行：

```bash
cd sample-lab
python -m pip install -e '.[dev]'
python -m pytest -q
unilab package inspect --path . --out dist/inspect
unilab package build --path . --out dist/build
```

预期自带的两项测试通过，设备包目录中有一个设备类型和一个普通工作流，并成功生成 wheel。`unilab package build` 会把默认启动图和本地配置收录到构建产物；后续新增的图片、模型等资产仍需按工作区规范声明打包规则。

需要验证运行时加载时，继续完成[下文的四道验证门](#workspace-validation)，使用 `dry-run + develop` 启动并检查状态。示例回显和构建通过仅证明基础骨架可用。

接入实际设备前，填写 `DEVICE_PACKAGE_REQUIREMENTS.md` 中的设备型号、协议、动作、参数单位、状态、异常和验收要求，再按[设备接入模板](device-template.md)、[物料定义模板](material-template.md)和[工作流](workflow.md)逐步替换教学示例。

下文说明设备包的文件职责和扩展规范。初始化已生成的文件可直接检查，并按实际业务补充；文档中的 `example_lab` 请替换为自己的 Python 包名。

## 设备包的文件组成与作用

```text
pyproject.toml ───────────────► 包名称、版本、依赖和 Python 导入目录
Python 包中的设备与物料定义 ─► 可用类型、动作、状态和资源合同
package.yaml ────────────────► 本次允许加载的工作流源文件
启动图 ──────────────────────► 本次启用的设备、物料、放置位和连接配置
                                      │
                                      ▼
                                 Uni-Lab OS
```

这四部分各有明确职责，不能互相替代：

| 文件或内容 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `pyproject.toml` | 包名称、版本、依赖和构建配置 | 不选择本次启用的设备实例 |
| 设备与物料定义 | 声明可用类型、动作、状态和约束 | 不保存现场连接地址 |
| `package.yaml` | 列出允许加载的工作流及其 UUID | 不登记设备或物料实例 |
| 启动图 | 创建实例、建立拓扑并提供非敏感连接配置 | 不自动加载未登记的工作流 |

## 步骤一：确定规范目录

下面的结构适合从零创建并长期维护一个设备包。`example_lab` 是示例 Python 包名，请替换为自己的业务名称，并在所有配置中保持一致。

```text
device-package/
├── pyproject.toml
├── package.yaml
├── example_lab/
│   ├── __init__.py
│   ├── common/                         # 多个设备共用的协议、日志和工具
│   ├── devices/                        # 设备类型、动作和驱动
│   ├── resources/                      # 物料、容器、仓库和放置位模板
│   ├── experiment_operations/          # 可复用实验操作
│   └── workflows/                      # 完整工作流
├── deployment/
│   ├── local_config.py
│   └── graphs/
│       ├── dry-run.json                # 模拟检查使用
│       └── production.json             # 真实环境使用
├── tests/                              # 合同、模拟和异常路径测试
└── README.md                           # 安装、启动、安全和恢复说明
```

:::{warning}
Python 导入包必须直接位于工作区根目录，并包含 `__init__.py`。不要改成 `<workspace>/src/example_lab/`，也不要同时维护两套包目录，否则 Uni-Lab OS 可能无法发现规范包。
:::

只创建实际需要的目录。设备和物料可以按业务领域继续分层，但工作流源文件必须在 `package.yaml` 中逐项登记。

## 步骤二：统一包身份

在 `pyproject.toml` 中声明设备包的名称、版本、依赖和启动文件：

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "example-lab"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["unilabos"]

[project.optional-dependencies]
dev = ["build>=1.2", "pytest>=8"]

[tool.setuptools.packages.find]
include = ["example_lab*"]

[tool.unilabos.startup]
graph = "deployment/graphs/dry-run.json"
config = "deployment/local_config.py"
ensure_dependencies = true
```

同一个设备包的身份必须前后一致：

| 用途 | 示例 | 约束 |
| --- | --- | --- |
| 发布名称 | `example-lab` | 写在 `project.name` 中 |
| Python 包目录 | `example_lab/` | 使用小写字母和下划线 |
| 清单包名 | `example_lab` | 与规范化后的 Python 包名一致 |
| 类型命名空间 | `community.example_lab` | 由检查结果确认，不手工另造一套名称 |

如需随包发布 CSV、JSON、YAML、图片或三维模型，应把相应扩展名加入 setuptools 的 package data。否则本地开发可能正常，构建后的安装包却会缺少资产。

设备驱动使用的第三方库应声明在 `dependencies` 中。密码、令牌和生产密钥不得写入 `pyproject.toml`、启动图或源码，应由运行环境的密钥配置提供。

## 步骤三：登记工作流

`package.yaml` 是允许加载的工作流清单：

```yaml
package:
  name: example_lab

workflows:
  - workflow_uuid: 41d51b13-8269-47cc-ad16-a553ed926f11
    source: example_lab/experiment_operations/standard_transfer.py
  - workflow_uuid: e96ea082-d18d-40da-907d-13cfc5b899af
    source: example_lab/workflows/sample_process.py
```

必须遵守以下约束：

- 顶层只写 `package` 和 `workflows`；
- 每个工作流只写 `workflow_uuid` 和 `source`；
- `source` 使用设备包内相对路径，且文件必须真实存在；
- UUID 必须与源码装饰器中的 `workflow_uuid` 完全一致；
- 同一 UUID 或路径不能重复；
- 暂时没有工作流时写 `workflows: []`，不能写 `null`；
- 位于 `workflows/` 的文件不会自动加载，仍然必须进入该清单。

设备和物料类型由 Python 包中的规范定义形成目录，具体写法见[设备接入模板](device-template.md)和[物料定义模板](material-template.md)。实例、连接参数和父子关系写入[启动文件](startup-files.md)，流程源码按[工作流](workflow.md)中的规范登记。

## 步骤四：准备本地配置

在 `deployment/local_config.py` 中保存非敏感的本地运行设置：

```python
class BasicConfig:
    ak = ""
    sk = ""
    disable_browser = True
    no_update_feedback = True
    log_level = "INFO"
```

本地开发时 `ak`、`sk` 保持为空。真实凭证使用环境变量或部署密钥注入，不得提交到设备包。

(workspace-validation)=
## 步骤五：通过四道验证门

先把命令中的路径替换为实际设备包绝对路径：

```bash
export DEVICE_PACKAGE_ROOT="/absolute/path/to/device-package"
cd "$DEVICE_PACKAGE_ROOT"
```

### 验证门一：依赖与 Python 包

```bash
python -m pip install -e '.[dev]'
python -m pip check
python -m compileall example_lab
```

只有三条命令都成功，才能继续。若 Python 包名不是 `example_lab`，最后一条命令使用实际目录名。

### 验证门二：设备包目录与合同

```bash
unilab package inspect \
  --path "$DEVICE_PACKAGE_ROOT" \
  --out "$DEVICE_PACKAGE_ROOT/dist/inspect"
```

检查报告中不得出现语法错误、重复 ID、重复 UUID、缺失源文件或无法解析的设备与物料类型。启动图中的 `class` 应从检查结果复制，不能依靠猜测填写。

### 验证门三：构建交付物

```bash
unilab package build \
  --path "$DEVICE_PACKAGE_ROOT" \
  --out "$DEVICE_PACKAGE_ROOT/dist/build"
```

构建完成后检查安装包和 Catalog 是否同时生成，并确认配置表、模型和图片等运行资产已经进入交付物。构建成功不代表真机已经连接。

### 验证门四：安全加载工作区

```bash
unilab workspace start \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --graph deployment/graphs/dry-run.json \
  --runtime-mode dry-run \
  --startup-mode develop \
  --wait 300 \
  --json

unilab workspace status \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --json
```

验收人员应确认：Uni-Lab OS 已就绪、设备包版本正确、设备与物料实例完整、工作流全部加载，并且没有真实设备动作。检查结束后停止工作区：

```bash
unilab workspace stop \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --wait 300 \
  --json
```

`dry-run` 只证明设备包发现、合同解析、启动图和工作流能够安全加载，不能证明真实驱动、现场联锁或物理动作已经通过验收。切换 `normal` 前必须另做隔离模拟器或受控真机验收。

## 步骤六：按小闭环逐步扩展

不要一次接入全部设备。推荐每次完成一个可验证的小闭环：

1. 增加一个设备或物料类型；
2. 在启动图中增加一个实例；
3. 编写一个只使用该实例的最小工作流；
4. 增加正常、超时和失败测试；
5. 重新执行检查、构建和 dry-run；
6. 验收通过后再接入下一个对象。

多个工站共用同一控制器时，只建立一个控制器连接，由各业务设备引用该连接；不要让每个设备重复建立会话。真实实现与模拟实现可以使用不同通信方式，但动作名称、参数、结果和状态合同必须一致。

## 常见问题

| 现象 | 常见原因 | 处理方式 |
| --- | --- | --- |
| 找不到规范 Python 包 | 包放在 `src/` 下、名称不一致或缺少 `__init__.py` | 把唯一的规范包直接放到工作区根目录 |
| `package.yaml` 无法读取 | 字段多写、漏写、重复或 `workflows: null` | 按本页封闭结构修改，空清单写 `[]` |
| 工作流没有出现 | 未登记源文件，或清单 UUID 与源码不一致 | 同步相对路径和 UUID 后重新加载 |
| 设备类型找不到 | 启动图中的 `class` 不存在或含义不明确 | 从 `package inspect` 结果复制完整类型名称 |
| 工作流绑定不到设备 | 工作流使用了设备类型 ID，而不是启动图实例 ID | 改为启动图中稳定且唯一的实例 ID |
| 本地可用、构建后缺文件 | 资产或子包没有进入构建配置 | 补充 package data 后重新构建并检查 |
| dry-run 成功但真实运行失败 | dry-run 不连接真实驱动 | 在隔离环境检查构造参数、通信、超时和联锁 |

## 交付前核对

- [ ] `project.name`、Python 包目录、`package.yaml` 和类型命名空间一致；
- [ ] 设备、物料、放置位和工作流身份稳定且唯一；
- [ ] 模拟与生产启动图分离，生产地址和密钥未进入源码；
- [ ] `package.yaml` 中每个源文件和 UUID 均可核对；
- [ ] 驱动依赖及运行资产完整进入交付物；
- [ ] 依赖检查、设备包检查、构建和 dry-run 全部通过；
- [ ] 真实运行前已完成连接、联锁、急停、取消和异常恢复验收；
- [ ] README 说明安装、启动、停止、升级和故障处理方式。
