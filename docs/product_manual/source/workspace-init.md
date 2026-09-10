# 初始化工作区（unilab workspace init）

:::{admonition} 阅读角色
- **业务负责人**：确定设备包用途、业务名称、负责人和保存位置。
- **开发人员**：创建目录和基础文件，并填写包身份与初始配置。
- **验收人员**：确认没有覆盖既有项目，且生成结构符合设备包规范。
:::

:::{warning}
当前版本尚未提供 `unilab workspace init` 子命令。现阶段请按照本页的“当前操作步骤”手工创建工作区，不要直接执行规划命令。
:::

## 这一步要得到什么

完成后，你会得到一个新的设备包项目骨架。它只包含目录和基础文件，还不能直接连接设备；接下来仍需填写设备、物料、启动图（Graph JSON）和工作流。

开始前由业务负责人确认：

| 项目 | 示例 | 要求 |
| --- | --- | --- |
| 设备包保存目录 | `/Users/name/labs/sample-lab` | 使用专用的新目录，不覆盖现有项目 |
| Python 包名 | `sample_lab` | 只用小写英文字母、数字和下划线，不能以数字开头 |
| 发布名称 | `sample-lab` | 对外识别名称，应能对应到 Python 包名 |
| 负责人 | `张三` | 负责版本、现场配置和交付确认 |
| 初始用途 | `样品前处理设备包` | 用业务语言说明设备包服务的场景 |

## 当前操作步骤

### 步骤一：设置名称与路径

打开终端，把下面两项替换为自己的值。目标目录必须尚不存在：

```bash
export DEVICE_PACKAGE_ROOT="/absolute/path/to/new-device-package"
export DEVICE_PACKAGE_NAME="sample_lab"
```

检查目标是否安全：

```bash
if [ -e "$DEVICE_PACKAGE_ROOT" ]; then
  echo "目标已存在，请换一个新目录"
else
  echo "目标目录可用，可以继续"
fi
```

看到“目标已存在”时立即停止，选择其他目录。没有输出表示可以继续。

### 步骤二：创建目录骨架

```bash
mkdir -p \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/devices" \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/resources" \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/experiment_operations" \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/workflows" \
  "$DEVICE_PACKAGE_ROOT/deployment/graphs" \
  "$DEVICE_PACKAGE_ROOT/tests"

touch \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/__init__.py" \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/devices/__init__.py" \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/resources/__init__.py" \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/experiment_operations/__init__.py" \
  "$DEVICE_PACKAGE_ROOT/$DEVICE_PACKAGE_NAME/workflows/__init__.py" \
  "$DEVICE_PACKAGE_ROOT/pyproject.toml" \
  "$DEVICE_PACKAGE_ROOT/package.yaml" \
  "$DEVICE_PACKAGE_ROOT/deployment/local_config.py" \
  "$DEVICE_PACKAGE_ROOT/deployment/graphs/dry-run.json" \
  "$DEVICE_PACKAGE_ROOT/README.md"
```

生成结果应为：

```text
new-device-package/
├── package.yaml
├── pyproject.toml
├── sample_lab/
│   ├── __init__.py
│   ├── devices/
│   ├── resources/
│   ├── experiment_operations/
│   └── workflows/
├── deployment/
│   ├── local_config.py
│   └── graphs/
│       └── dry-run.json
├── tests/
└── README.md
```

Python 包必须直接位于工作区根目录，并包含 `__init__.py`。不要把它放到额外的 `src/` 目录中。

### 步骤三：填写最小包身份

目录创建完成后，按照[工作区的“统一包身份”](workspace.md#步骤二统一包身份)填写 `pyproject.toml`。发布名称、Python 包名和清单包名必须指向同一个设备包。

在 `package.yaml` 中先写入：

```yaml
package:
  name: sample_lab

workflows: []
```

将 `sample_lab` 替换为步骤一确定的 Python 包名。尚未创建工作流时必须使用空列表 `[]`，不能写 `null` 或虚构源文件。

### 步骤四：准备安全的初始启动图

`deployment/graphs/dry-run.json` 只用于最初的结构检查，不填写生产设备地址、账号或密钥。至少先写入一个合法的空结构：

```json
{
  "nodes": [],
  "links": []
}
```

接入设备和物料后，再按照[启动文件](startup-files.md)增加实际实例。模拟配置与生产配置必须使用不同文件。

### 步骤五：记录交付信息

在 `README.md` 中记录：

- 设备包名称、用途和负责人；
- 当前版本及适用的 Uni-Lab OS 版本；
- 安装、启动和停止方法；
- 模拟与生产启动图的位置；
- 现场联锁、急停和异常恢复责任人；
- 已知限制和本次未接入的设备。

## 规划中的命令行为

后续版本提供该能力时，预期通过下面的形式指定生成目录：

```bash
unilab workspace init --output /absolute/path/to/new-device-package
```

`--output` 应创建新的设备包目录并生成与本页相同的骨架，不应覆盖已有目录。正式使用前必须先通过 `unilab workspace init --help` 确认当前安装版本已经提供该命令；若帮助信息中没有 `init`，继续使用上面的手工步骤。

## 完成标准

- [ ] 目标目录为新建的专用目录，没有覆盖已有设备包；
- [ ] Python 包直接位于工作区根目录，并包含 `__init__.py`；
- [ ] `pyproject.toml`、`package.yaml` 与 Python 包名一致；
- [ ] `package.yaml` 的空工作流清单写为 `workflows: []`；
- [ ] 初始启动图不包含生产地址、账号或密钥；
- [ ] README 已记录负责人、用途、版本和安全边界；
- [ ] 可以继续执行[工作区的四道验证门](workspace.md#步骤五通过四道验证门)。
