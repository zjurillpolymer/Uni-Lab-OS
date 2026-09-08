# 初始化工作区（unilab workspace init）

:::{admonition} 阅读角色
- **业务负责人**：确定设备包用途、业务名称、负责人和保存位置。
- **开发人员**：创建目录和基础文件，并填写包身份与初始配置。
- **验收人员**：确认没有覆盖既有项目，且生成结构符合设备包规范。
:::

:::{note}
当前版本已经提供 `unilab workspace init`。该命令只创建全新的工作区；目标路径已经存在时会直接失败，不会合并或覆盖任何文件。
:::

## 这一步要得到什么

完成后，你会得到一个带教学示例的设备包项目：一个无硬件副作用的回显驱动、一个调用该动作的工作流，以及只装载示例设备的 `dry-run` 启动图。它可以立即接受静态检查和测试，但还不能连接真实设备；接下来仍需填写真实设备、物料、启动图（Graph JSON）和工作流。

开始前由业务负责人确认：

| 项目 | 示例 | 要求 |
| --- | --- | --- |
| 设备包保存目录 | `/Users/name/labs/sample-lab` | 使用专用的新目录，不覆盖现有项目 |
| Python 包名 | `sample_lab` | 只用小写英文字母、数字和下划线，不能以数字开头 |
| 发布名称 | `sample-lab` | 对外识别名称，应能对应到 Python 包名 |
| 负责人 | `张三` | 负责版本、现场配置和交付确认 |
| 初始用途 | `样品前处理设备包` | 用业务语言说明设备包服务的场景 |

## 使用命令初始化

### 步骤一：设置名称与路径

打开终端，把下面两项替换为自己的值。目标目录必须尚不存在；包名可以使用发布形式 `sample-lab`，也可以使用 Python 形式 `sample_lab`：

```bash
export DEVICE_PACKAGE_ROOT="/absolute/path/to/new-device-package"
export DEVICE_PACKAGE_NAME="sample-lab"
```

执行初始化：

```bash
unilab workspace init \
  --output "$DEVICE_PACKAGE_ROOT" \
  --name "$DEVICE_PACKAGE_NAME"
```

`--name` 可以省略。省略时，命令会把输出目录名转换为包身份，例如目录 `sample-lab` 会得到发布名称 `sample-lab` 和 Python 包名 `sample_lab`。如果目标目录已存在，命令返回 `workspace_exists`，已有内容保持不变。

普通输出会直接显示工作区路径、两种包名、首先要填写的需求卡和下一组检查命令；自动化脚本或 Agent 使用 `--json` 可取得相同信息和 `nextCommands` 数组。

### 步骤二：检查生成的目录骨架

命令成功后会一次性生成：

```text
new-device-package/
├── .gitignore                         # 排除运行状态、构建和 Python 缓存
├── DEVICE_PACKAGE_REQUIREMENTS.md     # 先填写设备、物料、协议和验收事实
├── package.yaml
├── pyproject.toml
├── sample_lab/
│   ├── __init__.py
│   ├── devices/
│   │   ├── __init__.py
│   │   └── demo_device.py              # 示例设备和 echo 动作
│   ├── resources/
│   ├── experiment_operations/
│   └── workflows/
│       ├── __init__.py
│       └── demo_workflow.py            # 调用示例设备动作
├── deployment/
│   ├── local_config.py
│   └── graphs/
│       └── dry-run.json
├── tests/
│   └── test_workspace_contract.py     # 立即可运行的包身份与启动文件检查
└── README.md
```

Python 包必须直接位于工作区根目录，并包含 `__init__.py`。不要把它放到额外的 `src/` 目录中。

`demo_device.py` 的 `echo` 动作只回显输入文本，不连接或控制任何硬件；`demo_workflow.py` 展示设备类型导入、固定设备实例选择、节点 UUID、动作调用和结果返回。它们是可编译的教学示例，不代表真实设备能力。先运行 `python -m pytest -q` 和 `unilab package inspect --path . --out dist/inspect`，再根据 `DEVICE_PACKAGE_REQUIREMENTS.md` 中确认的设备资料、动作单位、物料位置和安全联锁替换示例。

### 步骤三：填写最小包身份

命令会按照[工作区的“统一包身份”](workspace.md#步骤二统一包身份)填写 `pyproject.toml`。发布名称、Python 包名和清单包名指向同一个设备包；初始版本为 `0.1.0`。

生成的 `package.yaml` 为：

```yaml
package:
  name: sample_lab

workflows:
  - workflow_uuid: f0e636c3-021e-5833-a9d5-da041f66fd8a
    source: sample_lab/workflows/demo_workflow.py
```

其中 `sample_lab` 会替换为步骤一确定的 Python 包名，工作流 UUID 会根据包名稳定派生，并与源码中的 `@workflow` 完全一致。删除教学工作流时，应同时删除这条清单记录；清单没有工作流时写 `workflows: []`，不能写 `null` 或不存在的源文件。

### 步骤四：准备安全的初始启动图

命令创建的 `deployment/graphs/dry-run.json` 只装载无硬件副作用的示例设备，不包含生产设备地址、账号或密钥。以 `sample-lab` 为例，其核心内容为：

```json
{
  "nodes": [
    {
      "id": "demo_device_01",
      "uuid": "579acffc-36dd-55bb-b3bf-90a1800b114e",
      "name": "示例设备",
      "class": "community.sample_lab.demo_device",
      "type": "device",
      "config": {},
      "data": {}
    }
  ],
  "links": []
}
```

`demo_workflow.py` 中的 `device("demo_device_01")` 必须与这里的 `id` 一致。接入设备和物料后，再按照[启动文件](startup-files.md)增加实际实例；模拟配置与生产配置必须使用不同文件，不能把真实连接参数补进这个教学图后直接上线。

### 步骤五：记录交付信息

在 `README.md` 中记录：

- 设备包名称、用途和负责人；
- 当前版本及适用的 Uni-Lab OS 版本；
- 安装、启动和停止方法；
- 模拟与生产启动图的位置；
- 现场联锁、急停和异常恢复责任人；
- 已知限制和本次未接入的设备。

## 命令参数与失败行为

查看当前安装版本的完整参数：

```bash
unilab workspace init --help
```

| 参数 | 是否必填 | 作用 |
| --- | --- | --- |
| `--output PATH` | 是 | 创建新的设备包工作区；目标必须不存在 |
| `--name NAME` | 否 | 指定包名；接受 `sample-lab` 或 `sample_lab`，省略时从输出目录名派生 |
| `--json` | 否 | 使用稳定 JSON 结果，便于脚本和 Agent 读取 |

命令在写文件前完成路径和名称校验。目标已经存在时返回 `workspace_exists`；包名不符合规范时返回 `invalid_package_name`；写入中途失败时会清理本次新建的目标，不留下半个工作区。

## 完成标准

- [ ] `unilab workspace init` 执行成功，目标目录为新建的专用目录；
- [ ] Python 包直接位于工作区根目录，并包含 `__init__.py`；
- [ ] `pyproject.toml`、`package.yaml` 与 Python 包名一致；
- [ ] `package.yaml` 已登记 `demo_workflow.py`，工作流 UUID 与源码一致；
- [ ] 已填写 `DEVICE_PACKAGE_REQUIREMENTS.md` 中的设备、物料、协议和安全事实；
- [ ] `python -m pytest -q` 已验证包身份、示例目录、启动图和示例驱动动作；
- [ ] `package inspect` 能发现一个示例设备定义和一个示例工作流定义；
- [ ] 初始启动图只含示例设备，不包含生产地址、账号或密钥；
- [ ] README 已记录负责人、用途、版本和安全边界；
- [ ] 可以继续执行[工作区的四道验证门](workspace.md#步骤五通过四道验证门)。
