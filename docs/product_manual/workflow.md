# 4. 工作流运行

:::{admonition} 阅读角色
- **业务负责人**：确认实验目的、输入输出、参数单位、成功标准和失败处理。
- **开发人员**：编写或编排节点、物料流、控制结构、设备绑定和正式合同。
- **验收人员**：执行静态检查、预检、模拟运行、异常路径和受控真机验收。
:::

```{toctree}
:maxdepth: 1

先理解工作流 <workflow-concepts>
工作流编排特性 <workflow-features>
实验操作 <experiment-operations>
完整工作流 <complete-workflow>
手写并运行第一个工作流 <first-workflow>
AI 编写工作流（推荐） <ai-workflow-authoring>
```

工作流把业务人员描述的实验步骤转换成 Uni-Lab OS 能检查、调度和追踪的流程。它只能使用用户设备包中已经登记的设备动作、物料模板和启动图（Graph JSON）实例，不能在工作流里重新实现设备通信。

## 完成本节后你将得到什么

- 一个可复用的实验操作；
- 一个调用该操作的完整工作流；
- 与源码一致的 `package.yaml` 登记；
- 一次静态检查、模拟运行和人工验收记录。

## 先分清两个层级

| 层级 | 适合做什么 | 示例 |
| --- | --- | --- |
| 实验操作 `experiment_operation` | 可被多个流程复用的单一业务能力 | 标准转运、开盖、恒温混合 |
| 完整工作流 `normal` | 从准备到结果的一次完整实验 | 取样、混合、检测并归位 |

一个实验操作只解决一个明确问题。完整工作流负责组合顺序、条件、并行、物料流和最终输出。

## 统一撰写规范

实验操作和完整工作流使用同一套静态定义规则。建议按“先写业务合同，再写节点，最后登记和验证”的顺序撰写。

### 文件与命名

| 对象 | 推荐写法 | 必须满足的约束 |
| --- | --- | --- |
| 文件名 | `standard_material_transfer.py` | 使用小写字母和下划线；一个文件只放一个主要定义 |
| 函数名 | `standard_material_transfer` | 与文件用途一致；发布后不要随意改名 |
| 页面名称 | `标准物料转运` | 使用业务人员看得懂的“对象 + 动作”名称 |
| `workflow_uuid` | 标准 UUID | 在整个设备包内唯一；同一定义持续使用，复制为新定义时重新生成 |
| 节点 UUID | `# unilab:node_uuid=<UUID>` | 紧邻对应节点、同一文件内唯一；移动或格式化已有节点时保持不变 |

`description` 不能只重复名称，应在一句话中说明“处理什么对象、完成什么结果、产生什么重要副作用”。例如：“搬运一件样品容器，并在设备确认成功后提交新的库位归属。”

### 输入合同

- 所有公开参数都放在函数参数中的 `*` 之后，调用时必须写参数名；
- 每个参数都声明类型；数值参数同时写业务名称、单位、最小值、最大值和合理默认值；
- 有固定选项时使用枚举或 `Literal`，避免让业务人员输入任意文本；
- 物料、容器、仓库等运行资源使用 `ResourceSlot`，不能使用名称字符串代替；
- 密码、令牌、生产地址和串口号不作为工作流公开参数，应由设备实例配置管理；
- 只有每次任务确实可能变化的值才公开。部署时固定的设备和仓库由启动图绑定。

### 节点写法

每个设备动作、物料来源、子工作流调用、条件、循环和展示分组都是需要稳定识别的节点。统一按下面的顺序写：

```python
# [可选业务标题]: 说明这一步为什么存在
# unilab:node_uuid=<稳定且唯一的 UUID>
result = device_selector.action_name(
    input_name=upstream.output_name,
    parameter_name=public_parameter,
)
```

- 动作只使用命名参数，参数名和结果字段必须与设备动作合同完全一致；
- 变量名描述动作完成后的状态，例如 `opened_container`、`sample_at_mixer`；
- 后一步读取前一步结果来建立依赖，不用注释中的序号代替数据连接；
- 不在工作流文件顶层执行网络请求、文件写入、设备连接或其他运行逻辑；
- 工作流是由 Uni-Lab OS 静态解析的定义文件，不作为普通 Python 脚本执行。

### 输出合同

正式业务输出使用 `TypedDict` 命名，并为每个字段声明类型。输出值只能来自公开输入、物料来源或节点实际结果。不得返回固定的 `True`、固定成功文本或计划位置来冒充设备执行结果。

对物料有影响的流程必须返回更新后的 `ResourceSlot`。目标量、设备回执量和实测量应使用不同字段，例如 `target_volume_ml`、`dispensed_volume_ml`、`measured_volume_ml`。

### 审查顺序

1. 业务审查：名称、目的、开始条件、成功标准和失败处理是否清楚；
2. 合同审查：输入、输出、单位、范围和资源类型是否完整；
3. 设备审查：实例、动作、参数和返回字段是否真实存在；
4. 物料审查：来源、流转、消耗、占用和最终位置是否连续；
5. 调度审查：顺序、并行、条件、循环和共享资源是否符合现场规则；
6. 运行审查：静态检查、预检、dry-run、失败路径和真实验收是否通过。

## 步骤一：业务人员填写需求卡

不要直接从代码开始。先用业务语言填写：

```text
流程名称：样品混合与归位
业务目的：将指定样品送到混合工站处理，完成后放回目标库位
输入物料：样品容器 1 个
输入参数：速度 rpm、时间 s
使用设备：搬运机器人、混合工站
开始条件：设备在线，来源有物料，目标位为空
成功标准：混合动作成功，样品位于目标库位
最长等待：搬运 60 s，混合 180 s
失败处理：停止后续动作，保留现场位置，通知操作员核对
输出：样品引用、最终库位、混合结果和消息
```

每个数值都写单位、允许范围和默认值。目标值与实测值必须使用不同字段名。

## 步骤二：把需求映射到设备包

开发人员制作映射表：

| 业务步骤 | 启动图实例 ID | 动作 | 关键参数 | 结果字段 |
| --- | --- | --- | --- | --- |
| 搬到工站 | `transport_robot_01` | `transfer_material_atomic` | 来源/目标仓库与放置位（Site） | `resource`、`site`、`result` |
| 混合 | `mixing_station_01` | `mix` | `speed_rpm`、`duration_seconds` | `sample`、`success`、`message` |
| 放回库位 | `transport_robot_01` | `transfer_material_atomic` | 最终仓库与放置位 | `resource`、`site`、`result` |

动作名、参数和返回字段必须从设备源码或 Catalog 复制。若某一项不存在，应先补设备动作，不得在工作流中猜测。

## 步骤三：准备目录和身份

```text
example_lab/
├── experiment_operations/
│   ├── __init__.py
│   └── standard_material_transfer.py
└── workflows/
    ├── __init__.py
    └── mix_sample.py
```

为每个工作流和每个持久节点生成一次 UUID：

```bash
python -c "import uuid; print(uuid.uuid4())"
```

UUID 写入源码后保持稳定。复制模板创建新流程时必须生成新 UUID；修改同一流程时不要无故更换。

## 步骤四：先写实验操作

先完成[实验操作（子工作流）](experiment-operations.md)。它应明确输入、输出、副作用和失败边界，并只在物理动作成功后提交一次物料位置变化。

## 步骤五：组合完整工作流

再按[完整工作流](complete-workflow.md)声明物料来源、调用实验操作、执行工艺动作并返回最终结果。

## 步骤六：登记 `package.yaml`

```yaml
package:
  name: example_lab

workflows:
  - workflow_uuid: 41d51b13-8269-47cc-ad16-a553ed926f11
    source: example_lab/experiment_operations/standard_material_transfer.py
  - workflow_uuid: e96ea082-d18d-40da-907d-13cfc5b899af
    source: example_lab/workflows/mix_sample.py
```

必须遵守：

- `workflow_uuid` 与对应源码装饰器完全一致；
- `source` 是设备包内相对路径；
- 只登记希望 Uni-Lab OS 加载的流程；
- 同一 UUID 和路径不能重复；
- 空清单写 `workflows: []`，不能写 `null`。

## 步骤七：执行检查

```bash
export DEVICE_PACKAGE_ROOT="/absolute/path/to/device-package"

python -m compileall \
  "$DEVICE_PACKAGE_ROOT/example_lab/experiment_operations" \
  "$DEVICE_PACKAGE_ROOT/example_lab/workflows"

unilab package inspect \
  --path "$DEVICE_PACKAGE_ROOT" \
  --out /tmp/device-package-inspect
```

检查报告中不得出现语法错误、重复 UUID、找不到的设备类型、动作或资源模板。

不要直接运行 `python mix_sample.py`。工作流文件是供 Uni-Lab OS 静态编译的 DSL，不是普通 Python 脚本。

## 步骤八：模拟启动和预检

```bash
unilab workspace start \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --graph deployment/graphs/simulation.json \
  --runtime-mode dry-run \
  --startup-mode develop \
  --wait 300 \
  --json
```

在 Uni-Lab OS 页面中：

1. 确认实验操作和完整工作流都已加载；
2. 检查输入名称、单位、范围和默认值；
3. 发布本次修订；
4. 运行零写入预检；
5. 使用测试物料创建 dry-run Task；
6. 查看每一步、等待原因、输出和物料位置变化；
7. 验证参数越界、设备离线和超时能明确失败。

## 修改与发布

已发布工作流应视为不可变合同。修改输入、输出、动作或资源关系时创建新修订，完成同样的检查和预检。正在运行的 Task 继续使用创建时冻结的版本；不要覆盖旧文件后假设旧任务会自动迁移。

## 提交与发布前核对

- [ ] 需求卡和动作映射表已确认；
- [ ] 实验操作职责单一，完整工作流边界清楚；
- [ ] 输入、输出、单位、范围和失败语义明确；
- [ ] 设备、物料、仓库和放置位都来自当前设备包与启动图；
- [ ] `package.yaml` 与源码 UUID/路径一致；
- [ ] 静态检查、设备包检查和 dry-run 通过；
- [ ] 资源等待、超时、取消和异常恢复经过验证；
- [ ] 真实运行前完成设备和现场安全验收。
