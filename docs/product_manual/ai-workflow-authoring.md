# AI 编写工作流（推荐）

:::{admonition} 阅读角色
- **业务负责人**：确认实验目的、输入输出、参数单位、成功标准和失败处理。
- **开发人员**：编写或编排节点、物料流、控制结构、设备绑定和正式合同。
- **验收人员**：执行静态检查、预检、模拟运行、异常路径和受控真机验收。
:::

本页假设设备包已经能被 Uni-Lab OS 加载，而且你已完成[工作流基础](workflow-concepts.md)、[用户设备包 手写教程](first-workflow.md)和[编排特性](workflow-features.md)。这些基础让你能够审查 AI 生成的 DSL，而不是直接相信生成结果。

若你还没有 `pyproject.toml`、设备定义、启动图（Graph JSON）和 `package.yaml`，先按[工作区](workspace.md)完成最小闭环。维护用户自己的设备包时，也可使用[AI 设备包生成器（实验性）](repository-builder-skill.md)，让本地 Coding Agent 协助修改或排查。

日常工作流创作推荐交给能够读取当前 Uni-Lab OS 与实验室设备包的 AI 编码助手：让它先从 Catalog、设备驱动、资源模板和 用户设备包 已登记流程中取证，再生成静态 Python DSL。人负责确认实验意图、审查证据、批准发布，并决定是否运行。

这不是“让 AI 猜一段 Python 后直接开设备”。推荐闭环是：

```text
实验需求
   │
   ▼
AI 只读扫描当前代码与 Catalog ──► 选择 用户设备包 相似流程
   │
   ▼
生成静态 DSL 草稿 ──► 人工审查 diff 与动作证据
   │
   ▼
产品静态编译 / 导入 ──► package inspect ──► 诊断归零
   │
   ▼
人工发布 ──► 零写入预检 ──► dry-run Task ──► 结果验收
   │
   └────────────────────────► 单独的真机安全验收
```

AI 负责提高创作效率；Uni-Lab OS 的编译器、发布合同、预检、调度和设备执行结果仍是判断“能否进入产品运行链路”的权威。AI 的文字回答或语法高亮不能代替这些检查。

## 当前支持到什么程度

| 环节 | 推荐工具 | 当前边界 |
| --- | --- | --- |
| 查找相似流程、驱动和资源 | 能读取两个仓库的 AI 编码助手 | 必须以当前检出的已跟踪代码为证据，不能凭模型记忆发明动作。 |
| 生成或修改源码 | AI 在个人草稿文件中生成静态 DSL | 新定义先生成草稿；不要直接执行该 Python 文件。 |
| 创建新定义 | Uni-Lab OS 页面/API 的“导入 Python” | 静态编译通过后，产品才原子写入设备包源码并登记 `package.yaml`。 |
| 修改现有定义 | Local Authoring 编辑链路 | 使用 draft → candidate → apply 的并发控制；不能把同一 UUID 当作新文件重复导入。 |
| 检查与观察 | Uni-Lab OS 页面、CLI；可选 MCP | MCP 能查看工作区/流程/Task 并等待创作修订，但当前没有生成、写入、导入、发布或预检工作流的 MCP 工具。 |
| 发布与运行 | 人在 Uni-Lab OS 页面明确确认 | `run_workflow` 会直接创建 Task；不要授权 AI 在未审查、未预检时调用。 |

因此，现阶段最稳妥的组合是“AI 读仓库和写草稿 + Uni-Lab OS 导入与运行”，而不是期待页面内有一个通用的“一键 AI 生成并运行”按钮。

## 1. 建立干净基线

先完成[系统安装](installation.md)，保持 `dry-run + develop`。在让 AI 修改任何内容前运行：

```bash
git -C "$LAB_ROOT/Uni-Lab OS" status --short
git -C "$LAB_ROOT/user-device-package" status --short
git -C "$LAB_ROOT/user-device-package" ls-files \
  'example_device_package/workflows/*.py'

cd "$LAB_ROOT/user-device-package"
./scripts/check-package.sh
mkdir -p workflow_drafts
```

记录检查结果和原有未提交修改。AI 必须保留与本次工作流无关的修改；若基线检查已经失败，先分清旧问题与新问题，不能把旧失败归咎于生成结果。

`git ls-files` 的结果是可作为产品示例的已跟踪流程清单。已跟踪文件本身若出现在 `git status` 中，也要先看 diff；需要锁定基线时让 AI 读取 `git show HEAD:<相对路径>`，不能把未提交内容冒充版本事实。不要让 AI 把本地未跟踪的验证夹具、临时产物或历史脚本当作产品语法依据。

## 2. 写清实验需求卡

先把需求写成这张卡，再交给 AI。信息不确定时写“待确认”，不要让 AI 自行补成看似合理的设备参数。

```yaml
目标: "这个流程最终完成什么实验结果"
流程类型: "normal 或 experiment_operation"
公开输入:
  - "名称 / 类型 / 单位 / 默认值 / 合法范围"
正式输出:
  - "名称 / 类型 / 来源"
步骤:
  - "按实验语义列出，不要先写代码"
允许使用的设备:
  - "设备业务 ID；未知时写待扫描"
物料与试剂:
  - "模板、来源工位、保管策略、用量与单位"
控制流: "条件 / 循环上限 / 可并行步骤"
共享资源: "设备、工位或区域互斥要求"
人工复核点: "哪些真实动作下发前必须确认"
目标 启动图: "要在哪一张部署 启动图 中编译和验收"
运行环境: "dry-run / 隔离 driver-sim / 真机"
验收结果: "dry-run 中应观察到的 Task、Job 和输出"
```

`normal` 表示可直接创建完整实验 Task；`experiment_operation` 表示先发布，再由其他流程复用。不能确定时，完整实验目标通常选 `normal`，可复用的局部工艺才选 `experiment_operation`。

## 3. 让 AI 先理解当前设备包

不要让 AI 根据设备名称猜测动作。应先让它读取用户设备包中本次要用的内容：

| 想实现的能力 | 必须检查 | 重点确认 |
| --- | --- | --- |
| 单设备动作 | 对应 `device.py` | 动作名、参数类型、单位、默认值和返回字段 |
| 条件与循环 | 编译器约束和已有安全测试流程 | 条件来源、最大循环次数和退出条件 |
| 物料搬运 | 资源模板、启动图 和原子搬运动作 | 来源、目标、占位、位置提交和失败恢复 |
| 并行处理 | 设备、工位和区域资源声明 | 哪些步骤可并行，哪些共享资源必须串行 |
| 可复用实验操作 | 已发布的操作合同 | 输入输出、版本和物料连续性 |
| 动态库位和数量记账 | 站点组与数量约束 | 候选站点、单位、预留、消费和回位 |

旧流程可能包含兼容写法或固定现场身份。创建新流程时，以当前编译诊断、设备动作合同和本次 启动图 为准；不能照抄设备 ID、物料 UUID、站点 UUID、体积或安全阈值。

AI 在写代码前至少要读取：

1. `package.yaml` 中的工作流登记；
2. 所选相似流程的完整源码；
3. 每个目标设备对应的 `devices/.../device.py` 动作签名与返回类型；
4. 使用到的 `resources/` 模板定义；
5. 本次 启动图 中的设备业务 ID、资源映射和动作模式；
6. Uni-Lab OS 的 `unilabos/workflow/authoring.py` 和相关编译约束，或本手册的[工作流编排特性](workflow-features.md)。

如果这些证据不能证明某个动作、参数、输出字段或资源存在，AI 应停在“待确认”，而不是生成猜测代码。

## 4. 复制这段提示词

把下面提示词和上一节的需求卡一起交给能访问当前工作区的 AI 编码助手；将 `<流程名>` 换成小写英文文件名。

```text
请为当前 user-device-package 工作区编写一个新的 Uni-Lab 静态 Python DSL 工作流。
代码事实优先级：当前 Uni-Lab OS 编译器 > 用户设备包驱动与 package.yaml >
设备包内已批准的工作流 > 我的自然语言描述。发现冲突时先报告，
不要自行猜测。

阶段 1 只读取证：
1. 记录 Uni-Lab OS、用户设备包和 启动图 的版本，确认使用的是本次批准配置；
2. 读取 package.yaml、指定 启动图、相关 device.py、资源模板和已批准的相似工作流；
3. 输出“需求步骤 → 设备动作 → 参数/返回类型 → 定义位置”的表；
4. 列出仍需我确认的设备 ID、站点、物料、单位、安全阈值、动作模式和并行假设。

阶段 2 生成草稿：
1. 仅在 workflow_drafts/<流程名>.py 写一个新定义，不改现有工作流，不改 package.yaml；
2. 使用现代 @workflow、绝对 import、带类型的关键字专用输入和真实设备类；
3. 每个动作、物料来源和持久控制结构使用唯一且稳定的 UUID 字面量；动作只用命名参数；
4. 输出只引用输入、物料来源或动作结果；不得发明 action、返回字段、资源或 Python DSL marker；
5. 条件、循环、并行、资源、物料和子工作流严格遵守当前编译器约束；
6. 物理搬运优先使用驱动已提供的原子动作，不拆成独立 pick/place/库存记账；
7. 没有现场证据时保留 presence、gripper payload 等驱动安全检查的默认值；
8. 不运行 python <流程名>.py，不发布工作流，不创建 Task，不连接或操作真实设备。

阶段 3 验证与交付：
1. 展示完整草稿、代码证据表、假设和人工复核项；
2. 只运行静态/只读检查，报告原始命令与结果；
3. 若诊断失败，只修复诊断明确指出的问题，不用删掉安全合同来换取通过；
4. 此阶段只证明草稿可交给产品导入，不宣称它已经通过 Uni-Lab 编译；
5. 导入、package inspect、发布、预检和运行都等待我确认。
```

如果 AI 在阶段 1 就发现需求缺少关键现场值，先回答它的问题。高质量生成的标志不是代码长，而是每个动作和资源选择都能追溯到当前仓库中的事实。

## 5. 审查 AI 草稿

导入前先逐项确认：

- 工作流 UUID、每个节点 UUID 都是唯一的固定字符串，修改代码时不会重新生成；
- 函数名和包内源码路径没有被当作排版随意改变；需要迁移身份时已同步检查 `package.yaml` 和引用方；
- 文件只包含允许的 import、设备声明、可选输出 `TypedDict` 和一个工作流函数；
- 所有设备类型、设备业务 ID、动作名、参数和结果字段都能定位到当前代码；
- 输入有类型、单位、范围和合理默认值，危险参数没有宽松默认值；
- 条件分支、循环上限和并行边界符合实验语义；
- `group` 没被误当成锁，`parallel` 没被误写成“保证物理同时”；
- 物料模板、来源、保管策略、站点与数量单位经过现场负责人确认；
- 没有硬编码从别的 用户设备包 流程复制来的物料实例 UUID 或 site UUID；
- 原子物理动作与唯一库存提交没有被 AI 拆成可分别调度的步骤；
- 普通值的 fan-out 与 `ResourceSlot` 的物理线性已经区分；无序分样由真实 split/aliquot Action 产生新身份；
- `check_source_presence`、`check_target_presence`、`check_gripper_payload` 等安全见证保持驱动默认值；任何关闭都有明确现场依据和审批人；
- 没有 `manual_confirm()` 之类不存在的 Python 语法；需要人工确认时，把该动作设计为实验操作，并在实验操作画布包装已绑定的真实设备动作；
- AI 没有顺手修改驱动、启动图、运行模式或无关文件。

需要改动时，把编译 diagnostic 原文连同行列号交回 AI，例如：

```text
只修复下面的 Uni-Lab 编译诊断，保留已经确认的实验语义、节点 UUID、
输入输出合同和安全约束。先解释根因与代码证据，再给最小 diff。
不要通过删除物料要求、缩短流程或改成未知动作来绕过错误。

<粘贴 diagnostic>
```

## 6. 用产品导入并验证

### 新工作流

在 Uni-Lab OS 的“工作流”页点击“导入 Python”，选择 `workflow_drafts/<流程名>.py`。产品会静态解析文件；完整候选通过后，才把规范源码写入设备包的 `workflows/`（实验操作写入对应目录）并向 `package.yaml` 追加登记。上传文件不会被 Python import 或执行。

导入要求当前 Workspace 恰好有一个可编辑的设备包源码目标。若返回 `source_target_unavailable`，先通过 `GET /api/v1/workspace/package-mounts` 检查 package mount 的 `editable` 状态，不要让 AI 猜测应写入哪个包。

导入成功后回到终端检查产品实际落盘结果：

```bash
cd "$LAB_ROOT/user-device-package"
git status --short
git diff -- package.yaml example_device_package/workflows
python -m unilabos.app.main package inspect --path .
./scripts/check-package.sh
```

同时在工作流详情确认：拓扑、输入输出合同、设备绑定、物料要求和 diagnostics 与需求一致。AI 草稿只是输入，产品保存的规范源码和编译图才是待发布候选。

涉及并行、组合流程、物料链或画布断边时，还要把产品生成的规范 Python 再次编译，并确认第二张图与第一张图语义等价。若出现 round-trip diagnostic，应保留原草稿，只让 AI 根据诊断做最小修复；不要使用 magic comment、空 `pass` 或伪 Fork/Join 绕过。

### 修改已有工作流

不要重复导入相同 UUID。先取得现有 authoring 修订和源码，让 AI 生成最小 diff，再通过 Local Authoring 的 draft → candidate → apply 链路提交；该链路使用 draft hash、工作流 revision 和 candidate hash 防止覆盖并发修改。应用后仍要重新运行本节的检查。

## 7. 人工批准发布和运行

只有下列条件全部满足后才发布：

1. AI 的动作证据表已经由人复核；
2. 编译 diagnostics 没有 error；
3. `package inspect` 和用户设备包检查通过；
4. 工作流详情中的图、合同和材料依赖正确；
5. 发布的是刚刚审查过的 revision。

发布后按[管理与运行工作流](workflows.md)执行零写入预检。第一次运行固定使用 `dry-run`；预检为 `runnable_now` 后，再由人创建 Task，并按[用户设备包 手写教程](first-workflow.md)的方法检查每个 Job、回执和正式输出。

`dry-run` 不构造设备驱动，因此只能证明编译、合同、调度和结果投影链路。需要验证仿真驱动时，下一阶段应明确选择隔离的模拟 启动图，并让 Uni-Lab OS 以真实动作模式构造仿真 Driver；它与真机 启动图 必须物理隔离。仿真 Driver 通过仍不证明真机联锁和运动安全。

真机运行是另一项验收。必须重新核对连接、急停、联锁、点位、夹具、载荷、库存、人员和恢复方案，不能因为 AI 生成成功或 dry-run 通过就自动切换到 `normal`。

## 可选：给 AI 接入 Workspace MCP

如果使用的 AI 客户端支持 MCP，可在已安装的源码环境中增加可选依赖：

```bash
cd "$LAB_ROOT/Uni-Lab OS"
python -m pip install -e ".[mcp]"
unilab-mcp --workspace "$LAB_ROOT/user-device-package"
```

在 AI 客户端中把命令配置为 `unilab-mcp`，参数使用 `--workspace` 和 用户设备包 绝对路径。具体配置文件格式由 AI 客户端决定。它是由本地 MCP Client 拉起的命令型 Server，不是 Uni-Lab 自带的公网 MCP 服务；不要暴露 Workspace Host 端口或本地 token。

MCP 适合让 AI 调用 `workspace_status`、`list_workflows`、`inspect_workflow`、`inspect_task` 和 `watch_task` 获取产品事实。开始时只授予读取和观察任务所需的能力。

`wait_authoring` 只适合等待工作流 revision 增长或非空诊断。同一 revision 下产生无诊断的有效 candidate 时，它可能超时；这时应读取 `/api/v1/workflows/{uuid}/authoring` 的最新状态。当前尤其要遵守六条边界：

- MCP 没有工作流源码生成、写入、导入、发布或运行前预检工具，生成仍由代码助手完成，写入仍走产品 Authoring/导入链路；
- `run_workflow` 会直接创建 Task，而且不能提交完整的库存绑定和优先级字段；涉及物料绑定时使用 Uni-Lab OS 页面或 HTTP API。它只能在人工明确批准且产品预检通过后调用；
- `run_workflow` 的 `operation_id` 只是关联元数据，不是创建 Task 的幂等键；响应不确定时先查询已有 Task，不能盲目重试；
- 不使用 `debug_workflow`，它仍指向已退役、固定返回 HTTP 410 的旧 Debug API；调试请创建标准 step Task。
- 不使用 `switch_workspace_authority`；该名字虽然仍被注册，当前 Workspace Host 会以 `backend_mode_removed` 拒绝；
- 真机环境不要用 MCP 的单组件 stop 代替 `unilab workspace stop`，后者才执行 Uni-Lab OS 的完整排空与停止顺序。

## 推荐的团队交付物

每个由 AI 辅助创作的工作流至少保留：

- 需求卡；
- AI 使用的参考文件清单；
- 动作/资源证据表；
- 工作流源码和 `package.yaml` diff；
- 编译与包检查结果；
- 发布 revision；
- 预检结果、dry-run Task UUID 和验收结论；
- 真机验收是否完成的独立状态。

这样后续维护者可以分清“AI 建议了什么”“产品验证了什么”“人批准了什么”和“设备实际执行了什么”。

## 后续日常使用

- 每次生成前让 AI 重新扫描当前 Catalog、驱动和相似流程，不复用过期动作记忆；
- 用[工作流编排特性](workflow-features.md)作为提示词约束与代码审查手册；
- 用[管理与运行工作流](workflows.md)完成发布、预检、Task 和修订管理。
