# 使用 AI 设备包生成器（实验性）

:::{admonition} 这页适合谁
- **业务负责人**：说明设备、动作、单位、现场限制和交付目标，不需要编写代码。
- **开发人员**：让 Coding Agent 在明确边界内创建或修改设备包，并运行当前仓库支持的检查。
- **验收人员**：区分静态检查、构建、模拟加载和真机验收，不把较低等级的证据写成生产通过。
:::

当前 `Uni-Lab-OS` 仓库已经提供 `unilab-domain-repo-builder` Skill。它可以协助新建设备包、迁移旧代码或分层诊断设备包问题，但不会自动知道实验室现场事实，也不能代替人工审查和产品验收。

:::{warning}
这不是一键生成器。地址、单位、超时、联锁、物料位置、工作流 UUID 和凭证必须来自用户确认的资料。资料缺失时，AI 应停止猜测并列出待确认项。
:::

## 当前仓库中可以使用的内容

先将本机的 Uni-Lab OS 源码目录填写为通用变量：

```bash
export UNILAB_ROOT="/absolute/path/to/Uni-Lab-OS"
```

在该源码仓库中可以核对到：

| 路径 | 用途 |
| --- | --- |
| `$UNILAB_ROOT/` | Uni-Lab OS 源码、CLI、设备包合同和产品手册 |
| `$UNILAB_ROOT/.cursor/skills/unilab-domain-repo-builder/SKILL.md` | 新建、迁移、诊断和验证设备包的 Coding Agent 指南 |
| `$UNILAB_ROOT/.cursor/skills/unilab-domain-repo-builder/references/` | 包模板、装饰器和 Workflow Python 合同 |
| `$UNILAB_ROOT/.cursor/skills/add-device/SKILL.md` | 编写单个设备驱动时的补充参考 |
| `PLC-Sim/` | 可选的 PLC、OPC UA 和 Modbus 联调工具；仅在设备包明确需要时使用 |

先在终端执行只读检查：

```bash
test -f "$UNILAB_ROOT/setup.py"
test -f "$UNILAB_ROOT/unilabos/package_manager/cli.py"
test -f "$UNILAB_ROOT/.cursor/skills/unilab-domain-repo-builder/SKILL.md"
test -f "$UNILAB_ROOT/.cursor/skills/add-device/SKILL.md"
```

四条命令都不输出错误，才说明本页引用的 Uni-Lab OS 文件在当前仓库中存在。`PLC-Sim` 是可选工具，不是设备包开发或 Uni-Lab OS 启动的必需条件。

## AI 能做什么

| 场景 | 可以请 AI 完成 | 必须由人确认 |
| --- | --- | --- |
| 新建设备包 | 创建包结构、清单、设备和工作流骨架，补充测试 | 业务名称、设备型号、动作含义、单位和交付范围 |
| 迁移设备包 | 盘点旧代码，逐步迁移装饰器、清单、模拟器和测试 | 兼容范围、现场协议和允许删除的旧能力 |
| 修改设备 | 找到同类实现，小范围修改 Driver、模拟器、启动图和测试 | 地址表、参数、超时、安全联锁和恢复方式 |
| 排查失败 | 按 Package、Registry、Catalog、Authoring、Runtime 分层定位 | 现场连接、硬件故障和真机验收结论 |

AI 不应连接真机、启动实验、发布包、写入凭证或更改生产配置，除非业务负责人对本次任务明确授权。

## 第一步：确认目标设备包

设备包是用户自己的项目，不由本手册虚构名称。先取得它的绝对路径，并确认至少包含以下文件：

```bash
export DEVICE_PACKAGE_ROOT="/absolute/path/to/user-device-package"

test -f "$DEVICE_PACKAGE_ROOT/pyproject.toml"
test -f "$DEVICE_PACKAGE_ROOT/package.yaml"
test -f "$DEVICE_PACKAGE_ROOT/deployment/local_config.py"
```

如果文件缺失，不要从其他项目复制现场数据。新项目应先按[手工初始化工作区](workspace-init.md)创建空骨架，再填写自己的包身份和配置。

## 第二步：填写需求卡

把下面内容复制到任务中。不会填写的项目写“待确认”。

```text
任务类型：新建 / 迁移 / 修改 / 只读排查
目标设备包绝对路径：
业务目标：完成后用户能够做什么

发布名称与 Python 包名：
设备名称和型号：
通信协议：串口 / Modbus / OPC UA / HTTP / 其他
协议资料或地址表：文件路径、版本和负责人
动作：名称、输入、单位、输出、超时和失败表现
状态：需要展示或记录的状态、单位和更新频率

资源与放置位：容器、载架、父子关系和允许位置
目标工作流：输入、输出、顺序、并行和失败条件
模拟范围：可以模拟什么，哪些项目必须真机确认

允许 AI 执行：只读 / 修改代码 / 运行测试 / 构建 / dry-run
禁止 AI 执行：连接真机 / 启动任务 / 发布 / 写入凭证 / 其他
完成标准：本次允许执行到哪一道验证门
```

业务负责人至少确认业务目标、动作含义、单位、失败表现、现场限制和完成标准。技术字段可以由开发人员补充，但必须注明资料来源。

## 第三步：把任务交给 Coding Agent

将下面提示词中的路径替换为实际设备包路径，然后连同填写好的需求卡一起提交：

```text
请使用以下本地 Skill 处理 Uni-Lab OS 设备包任务：
<Uni-Lab-OS 源码绝对路径>/.cursor/skills/unilab-domain-repo-builder/SKILL.md

如需修改单个设备驱动，再读取：
<Uni-Lab-OS 源码绝对路径>/.cursor/skills/add-device/SKILL.md

目标设备包：/absolute/path/to/user-device-package

开始前先读取目标设备包内实际存在的 AGENTS.md、pyproject.toml、package.yaml、
README、目标启动图和相关测试，并报告 Git 状态。使用实际运行该设备包的 Python，
输出 sys.executable、unilabos.__file__ 和 pip show unilabos。不要根据相邻目录、
旧文档或其他设备包猜测版本和现场事实。

先列出已知事实、待确认项、拟修改文件和验证计划。每次只完成一个可验证的小闭环。
不要发明设备、动作、单位、地址、NodeId、资源关系、UUID、超时、联锁或凭证；
保留已有修改，不覆盖无关工作。未经需求卡明确授权，不连接真机、不启动实验、
不发布、不写入密钥。

修改后按产品手册的依赖与 Python 包、package inspect、package build 和 dry-run
验证门逐项检查。报告每条命令、退出状态、运行模式、关键结果、剩余风险和人工待办。
任何一道门失败，都不要声称设备包已经可用。

需求卡：
<粘贴填写后的需求卡>
```

如果本轮只需要诊断，在提示词第一行补充：

```text
本轮只做只读排查，不修改文件、不安装依赖、不启动服务、模拟器或设备。
```

## 第四步：人工审查修改

运行服务前，先由开发人员检查改动。下面命令中的路径必须是已经确认的设备包路径：

```bash
git -C "$DEVICE_PACKAGE_ROOT" status --short
git -C "$DEVICE_PACKAGE_ROOT" diff
```

至少确认：

- 修改只发生在目标设备包，没有覆盖其他人的工作；
- 没有密钥、令牌、生产地址或个人信息；
- `pyproject.toml`、Python 包目录和 `package.yaml` 使用同一包身份；
- 动作名称、参数、类型、单位、返回值和状态符合需求卡；
- 真实驱动与模拟器使用相同的动作合同；
- 启动图中的实例和连接配置有明确来源；
- 工作流没有复制其他项目的现场 UUID、地址或物理布局。

有任何现场事实无法确认时，停止验收，回到需求卡补充。

## 第五步：按验证门检查

先激活当前安装使用的环境，并确认 Python 来源：

```bash
mamba activate unilab
export UNILAB_ROOT="/absolute/path/to/Uni-Lab-OS"
export DEVICE_PACKAGE_ROOT="/absolute/path/to/user-device-package"
cd "$DEVICE_PACKAGE_ROOT"

python -c 'import sys, unilabos; print(sys.executable); print(unilabos.__file__)'
python -m pip show unilabos
```

### 验证门一：依赖和 Python 包

```bash
python -m pip install -e '.[dev]'
python -m pip check
python -m compileall <实际的_Python_包目录>
```

尖括号中的内容必须替换为 `pyproject.toml` 中登记并实际存在的 Python 包目录。不要直接复制占位符执行。

### 验证门二：设备包目录与合同

```bash
unilab package inspect \
  --path "$DEVICE_PACKAGE_ROOT" \
  --out "$DEVICE_PACKAGE_ROOT/dist/inspect"
```

报告中不能有语法错误、重复 ID、重复 UUID、缺失源文件或无法解析的类型。

### 验证门三：构建交付物

```bash
unilab package build \
  --path "$DEVICE_PACKAGE_ROOT" \
  --out "$DEVICE_PACKAGE_ROOT/dist/build"
```

检查 wheel、Catalog 和设备包需要的配置、模型及图片是否都进入交付物。构建成功不代表设备已连接。

### 验证门四：安全加载

只有需求卡明确允许启动本地组件时才执行，并将启动图替换为设备包中真实存在的模拟或隔离测试文件：

```bash
unilab workspace start \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --graph deployment/graphs/<实际的测试启动图>.json \
  --runtime-mode dry-run \
  --startup-mode develop \
  --wait 300 \
  --json

unilab workspace status \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --json

unilab workspace stop \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --wait 300 \
  --json
```

`dry-run` 只证明 Uni-Lab OS 能在安全模式发现和加载设备包，不能证明通信、联锁、急停或物理动作正确。

## 如何写验收结论

| 已取得的证据 | 可以得出的结论 | 不能得出的结论 |
| --- | --- | --- |
| Python 编译成功 | 源码可解析 | 设备包合同正确 |
| `package inspect` 成功 | 包结构和静态合同可检查 | 运行时或真机正常 |
| 测试及 `package build` 成功 | 已覆盖测试通过，交付物可生成 | 所有现场场景都已覆盖 |
| Workspace `dry-run` 成功 | 产品可安全发现并加载设备包 | 模拟器或真机已经通过 |
| 隔离模拟器通过 | 指定的模拟行为通过 | 真实硬件和联锁正确 |
| 受控真机验收通过 | 记录中覆盖的硬件场景通过 | 未验收的型号或工况也通过 |

推荐写法是：“已通过 Package 检查、构建和 dry-run，真机未验收。”不要只写“设备包已完成”。

## 常见失败

| 现象 | 处理方式 |
| --- | --- |
| 找不到 Skill | 确认 `$UNILAB_ROOT` 指向当前 Uni-Lab OS 源码仓库，再检查上文列出的实际文件路径 |
| `ModuleNotFoundError` | 核对 `sys.executable` 和 `unilabos.__file__`，切换到实际 Uni-Lab 环境 |
| `package inspect` 失败 | 从第一条错误开始修复包名、清单、源码、UUID 或注册信息 |
| 构建后缺文件 | 补充 `pyproject.toml` 的 package data 配置，再重新构建和检查 wheel |
| dry-run 成功、真机失败 | 单独检查协议、地址、超时、联锁和硬件状态，不把 dry-run 当真机证据 |

设备包每个文件的职责和完整验证要求见[工作区](workspace.md)；单个设备驱动的业务模板见[设备接入模板](device-template.md)。
