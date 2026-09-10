---
orphan: true
---

# 使用 AI 设备包生成器（实验性）

:::{admonition} 阅读角色
- **业务负责人**：确认设备包范围、现场对象、业务名称和交付目标。
- **开发人员**：建立目录、登记清单、依赖、启动图和测试。
- **验收人员**：确认设备包能够被检查、加载、模拟启动并留下版本记录。
:::

`unilab-domain-repo-builder` 是本地 UniLab Workbench 随附的 Coding Agent Skill。它帮助新手把实验室事实整理成可维护的设备包，也可以迁移旧 Driver，或诊断 Package、Registry、Catalog、工作流往返和运行加载问题。

这是安装主路径之外的可选开发分支。没有 Workbench 或 Agent 时，Uni-Lab OS 页面、CLI 和工作流运行仍然可用；用户可以直接按[工作区](workspace.md)手写同一份设备包合同。

:::{warning}
这是辅助开发能力，不是一键生成器，也不代表生产就绪。AI 生成的代码必须经过人工审查和产品验收。Uni-Lab OS 业务页面没有 Agent 入口；本页操作只适用于安装在开发机上的本地 Workbench。
:::

## 它负责什么

| 场景 | 可以请 AI 完成 | 它不负责 |
| --- | --- | --- |
| 新建设备包 | 建立包身份、目录、设备、资源、启动图（Graph JSON）、工作流和测试骨架 | 猜测真实地址、单位、联锁或物料事实 |
| 迁移设备包 | 盘点旧代码，逐步迁移装饰器、清单、模拟器和验证链路 | 静默删除兼容代码或改写现场协议 |
| 诊断设备包 | 按 Package → Registry → Catalog → Authoring → Runtime 分层定位失败 | 用后层绕过前层错误，或把仿真成功写成真机通过 |

完整的设备包加载合同仍以[工作区](workspace.md)为准。Skill 负责读取事实、生成或修改代码和执行检查，不取代 Uni-Lab OS 的编译器、任务调度、库存权威或安全联锁。

## 前置条件

开始前应准备：

- 已按[开发工具与接口](interfaces.md#本地安装与启动)中的说明启动本地 UniLab Workbench；
- AionUi `2.1.52+` 的本地 Agent 载荷；非默认位置用 `UNILAB_AIONUI_APP` 指定，且不要设置 `UNILAB_AGENT_ENABLED=0`；
- 一个已经存在、可写且至少含 `deployment/local_config.py` 的 Workspace 目录；
- 该 Workspace 实际使用的 Uni-Lab OS Python 环境；
- 设备协议、地址表、参数单位、资源与放置位（Site）、目标工作流和仿真范围；
- Git 状态或其他可回退副本，且真实凭证没有写入需求卡。

新建设备包不能直接从完全空的目录启动；桌面 Workbench 欢迎页会拒绝不含 `deployment/local_config.py` 的目录。先按下一节创建最小启动壳，再把设备包根目录选为 Workspace。

不要让 Agent 在错误的父目录、另一个设备包或无法回退的共享目录中工作。

## 为新设备包创建启动壳

先建立下面两个目录层级；文件必须位于目标设备包根目录之下，而不是放在它的父目录：

```text
new-lab/
└── deployment/
    └── local_config.py
```

把以下最小配置写入 `deployment/local_config.py`：

```python
class BasicConfig:
    ak = ""
    sk = ""
    disable_browser = True
    no_update_feedback = True
    log_level = "INFO"
```

这一步只让 Workbench 能识别并打开该 Workspace，以便独立启动的 Agent 继续建立 Package。此时默认 启动图 和包结构尚不存在，Uni-Lab OS 启动失败是预期现象；它不代表设备包已可安装或能启动设备。不要在文件中填写真实密钥。

## 在 Workbench 中确认 Agent 和 Skill

1. 在 Workbench 中选择目标 Editable Package，确认标题或环境管理器中的 `Workdir` 指向目标 Workspace。
2. 打开“环境管理”，等待 Agent 卡片显示“工作区 Agent 已就绪”；未启动时点击“启动 Agent”。
3. 点击 Activity Bar 中的“Agent”，确认右侧面板显示当前 Workspace 名称。
4. 在 Workbench 终端中执行下面的只读检查：

```bash
test -f .agents/skills/unilab-domain-repo-builder/SKILL.md \
  && echo "repository builder ready"
```

Workbench 启动所选 Workspace 的 Agent 时，会先把随应用打包的托管 Skill 播种到 `<workspace>/.agents/skills/`，再以该 Workspace 为 Agent 工作目录。Skill 不存在时，不要让 Agent 假装已经读取；先按[失败与回退](#失败与回退)处理。

托管 Skill 采用内容摘要管理。未改动的旧副本可以随 Workbench 更新；预先存在或由用户修改过的目录会被播种逻辑保留，不会被新版载荷静默覆盖。需要升级定制版本时，应先比较差异并人工合并。

## 先填写新手需求卡

把未知项明确写成“待确认”，不要让 AI 用合理猜测填充实验室事实。

```text
任务类型：新建 / 迁移 / 诊断
目标设备包绝对路径：
distribution 名称与 import package：
设备：名称、协议、动作、参数单位、结果、状态：
地址表或供应商资料位置：
资源与 放置位：模板、实例、父子关系、可用位置：
目标工作流：输入、输出、顺序、并行、失败条件：
模拟器：类型、端点、已覆盖的握手行为：
禁止事项：真机连接、发布、运行、凭证写入等：
完成标准：本次允许执行到哪一道验证门：
```

地址、单位、超时、联锁和现场恢复规则缺失时，AI 应停在接口骨架或模拟层，并列出待确认项。它不应从 用户设备包 示例复制设备实例 ID、NodeId、Workflow UUID 或物理布局。

## 可复制提示词

```text
请使用 unilab-domain-repo-builder Skill 处理下面的设备包任务。

先读取设备包内的 AGENTS.md、pyproject.toml、package.yaml、目标 启动图、
地址表和现有测试，再确认 Git 状态。使用将实际运行该设备包的 Python，
输出 sys.executable、unilabos.__file__ 和 pip show unilabos；不要根据
相邻目录猜测 OS 版本或装饰器合同。

按“包与导入 → 资源和 放置位 → 设备与模拟器 → Typed Actions → 最小叶子
Workflow → 组合 Workflow → 产品验收”的依赖顺序工作。真实 Driver 与
模拟器保持相同动作、参数、结果和 topic 合同，只替换传输层。

先列出已知事实、未知项、拟修改文件和验证计划。不要发明设备、动作、
单位、PLC 地址、资源、API 或 UUID；不要连接真机、发布或运行任务，除非
我在需求卡中明确授权。保留已有修改，不覆盖无关工作。

完成后按产品手册的 Package inspect、Registry check、package build 和
dry-run 门逐项验证。报告每道门的命令、结果、运行模式、剩余风险和人工
待办；任何一道门失败都不要声称设备包已经可用。

需求卡：
<粘贴填写后的需求卡>
```

如果只想诊断，不想修改，请在首句追加：“本轮只读诊断，不修改文件、安装依赖、启动设备或运行任务。”

## AI 应按什么顺序工作

1. 读取设备包规则、Git/依赖状态、清单、启动图、地址表和测试，列出已知与未知事实。
2. 从实际 Python 解释器解析 `unilabos` 位置和版本，再核对当前装饰器与工作流合同。
3. 先让 packaging、imports 和清单可检查，再登记稳定的资源模板、物理资源与 放置位。
4. 每次只增加一个设备垂直切片：Driver、启动图 实例、模拟 transport、Typed Action 和最小叶子 Workflow。
5. 叶子 Workflow 通过后再添加组合 Workflow；先加载子流程，再验证父流程达到稳定固定点。
6. 验证 Python → AST → 启动图 → Python → 启动图 的语义固定点，不用魔法注释、空 `pass` 或无效 Fork/Join 保存拓扑。
7. 最后运行允许范围内的模拟器和 Workbench 验收；真机证据必须单独记录。

这一顺序避免在包身份、资源或动作合同尚未稳定时先堆叠复杂流程。AI 若建议修改 Uni-Lab OS 或共享页面，应先说明为何问题不属于设备包，并把系统修改作为独立决策。

## 人工审查生成结果

在接受修改前，至少核对以下内容：

- Git diff 只包含目标设备包文件，没有删除用户改动、写入密钥或夹带构建产物；
- distribution、import package、`package.yaml` 和 `community.*` 身份一致；
- 启动图 中的实例、端点、父子关系和配置来自用户设备包事实；
- Action 参数名、类型、单位、默认值、超时和结果与 Driver 一致；
- real/simulator 的动作与 topic 合同一致，差异只在传输和配置；
- Workflow 使用 启动图 实例 ID，节点 UUID 稳定，物料身份和输入绑定没有被复制或猜测；
- dry-run、模拟器和真机证据被明确分开，失败与未知结果有恢复说明。

AI 生成的 README、注释和测试也可能复述错误假设。审查时应回到当前代码、供应商协议、地址表、活动 启动图 和现场验收记录，而不是用生成文本证明生成文本正确。

## 继续走产品验收门

生成完成后，按设备包教程中的[四道验证门](workspace.md#步骤五通过四道验证门)继续验收：

1. [验证门一：依赖与 Python 包](workspace.md#验证门一依赖与-python-包)，确认依赖、导入包和 Python 语法。
2. [验证门二：设备包目录与合同](workspace.md#验证门二设备包目录与合同)，确认包身份、设备、物料和工作流清单。
3. [验证门三：构建交付物](workspace.md#验证门三构建交付物)，防止本地可用但发布包缺少文件。
4. [验证门四：安全加载工作区](workspace.md#验证门四安全加载工作区)，只用 `dry-run + develop` 核对 Uni-Lab OS 整体状态、设备连接与工作流。

四道门全部通过，也只证明设备包可被安全模式发现、编译和加载。连接隔离模拟器、PLC-Sim 或真机前，继续执行同页的运行边界，并分别记录模拟器与物理见证证据。

## 失败与回退

| 现象 | 处理方式 |
| --- | --- |
| Workbench 没有 Agent 入口 | 确认使用本地 Theia Workbench，而不是 Uni-Lab OS 业务页面；改按手工设备包教程继续 |
| Agent 显示启动失败 | 在环境管理器查看 Agent 日志，核对本地 Agent 载荷与 Workspace 可写性，再重试 |
| Skill 文件不存在 | 重启所选 Workspace 的 Agent；仍缺失时更新或修复 Workbench，不让 Agent 凭记忆生成 |
| Skill 没有随新版更新 | 检查目标 Skill 目录是否有用户修改；保留定制副本，人工比较新版后合并 |
| AI 修改方向错误 | 停止 Agent，检查 Git diff，回退本轮目标文件，再用更完整需求卡重新开始 |
| 某道验证门失败 | 保留原始诊断，从最早失败层修复；不要跳到 Workbench 或真机掩盖错误 |
| 只有仿真通过 | 标记为模拟证据，保持真机未验收，不切换 `normal` |

如果没有可用 Agent，产品主路径不受影响。可以完全按照[工作区](workspace.md)手工实现，再使用[用 AI 编写工作流](ai-workflow-authoring.md)中的审查提示词辅助后续工作流。

## 当前边界

- 该 Skill 只随本地 Workbench Agent 使用，Uni-Lab OS 业务页面没有对应入口。
- 它是可修改代码的 Coding Agent 指南，不是服务器端建仓 API，也不是无人值守流水线。
- `evals/evals.json` 目前只记录场景提示词和期望输出，不是这些场景已经运行或通过的证明。
- Skill 不提供实验室事实、供应商保证、物理联锁或硬件见证，不能据此声明生产就绪。
- 生成设备包仍必须通过 Package、Registry、Catalog、Authoring、模拟器和所需硬件的分层验收。
