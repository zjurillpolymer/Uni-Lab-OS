# 故障排查

:::{admonition} 阅读角色
- **业务负责人**：提供使用场景和预期结果，不直接操作调试接口或恢复命令。
- **开发或运维人员**：使用开发工具、接口和日志定位并处理问题。
- **验收人员**：确认权限、输入输出、异常处理和操作记录符合要求。
:::

先判断问题属于页面连接、定义/输入、资源等待、设备执行还是恢复状态。保留任务 UUID、节点 UUID、Job UUID、时间和 Trace ID，再进行操作。

## 安装与本地启动

### `unilab` 命令不存在

先激活安装 Uni-Lab OS 的 Conda 环境，再检查 `python -m pip show unilabos`。源码安装还应确认 `pip install -e .` 和 `uv pip install -r unilabos/utils/requirements.txt` 已成功结束。不要在系统 Python 和 Conda Python 之间混装。

### `import rclpy` 失败

完整 Uni-Lab OS 即使在 dry-run 中也会初始化 ROS。只创建裸 Python 环境不够；按[环境与运行配置](environment.md#选择-conda-环境)安装 `unilabos-env`、`unilabos` 或 `unilabos-full`。

### `import yaml` 失败

Uni-Lab OS 启动时需要导入 `PyYAML`。在已激活环境执行：

```bash
python -m pip install "PyYAML>=6"
```

### Health 正常但 `/console/` 返回 404

干净源码不带已编译 React bundle。在 `Uni-Lab OS/frontend` 中确认 Node ≥22.13，然后执行 `npm ci && npm run build`；看到 `unilabos/app/web/static/console/index.html` 后重启 Workspace。

### `--skip_env_check` 或 `--test_mode` 不识别

这是旧脚本参数。当前解析器明确拒绝，改用：

```bash
unilab workspace start \
  --workspace /absolute/path/to/user-device-package \
  --graph deployment/graphs/example_lab-local-debug.json \
  --runtime-mode dry-run \
  --startup-mode develop \
  --wait 300 \
  --json
```

### Uni-Lab OS 页面可用但设备连接未就绪

网页/API 可用只证明 Uni-Lab OS 的访问入口正常。设备连接未就绪时，读取内部设备运行日志：

```bash
unilab workspace logs \
  --workspace /absolute/path/to/user-device-package \
  --component edge \
  --json
```

检查 ROS 环境、启动图（Graph JSON）、用户设备包 Catalog 和动态端口。不要改用 `--backend simple`；当前完整实现只支持 ROS backend。

## 快速健康检查

管理员可以先从 `unilab workspace status --json` 取得 Uni-Lab OS API 地址，再用以下只读接口检查：

```bash
curl -fsS "$BACKEND_URL/api/v1/health"
curl -fsS "$BACKEND_URL/api/v1/readiness"
curl -fsS "$BACKEND_URL/api/v1/edge/readiness"
```

正常情况下，Uni-Lab OS 和工作流运行时应为 `ready`，设备连接应为 `connected: true`，且设备数量与本次 启动图 一致。

## 连接与页面问题

### Uni-Lab OS 页面无法打开

1. 访问 `/api/v1/health`，区分 Runtime 不可用和静态资源问题。
2. 确认 URL 以 `/console/` 结尾。
3. 如果 API 正常而页面返回 404，运行镜像可能没有包含前端 bundle。
4. 如果返回 403，检查 Host allowlist 和浏览器同源来源。

### 页面显示重连中或只读快照

不要继续提交写操作。检查 Readiness、网络和 Pod 状态，等页面重新显示在线后刷新数据。只读快照是最后一次成功结果，不代表当前设备/库存事实。

### 设备未连接或设备数为 0

检查 Uni-Lab OS 运行实例、设备控制连接、活动 启动图 和设备注册错误。设备注册至少需要一台有效设备，并会校验本地 ID、动作和绑定材料唯一性。恢复连接后再次查看在线设备，不要直接重试在途物理动作。

### PLC 仿真器页面可打开，但设备动作没有响应

GUI 健康只证明 Web 进程存在。按[PLC / OPC UA 仿真器](plc-sim.md)依次检查 OPC UA Server、可选握手代理和 Uni-Lab OS 设备会话；所需组件必须同时就绪。再确认活动 启动图 使用设备包部署说明提供的协议地址，且对应 PLC 实例在线。

如果任务已经越过派发边界，不要通过重启 Server/Agent 或重建 Task 来重试。先停止新派发，核对 Job、PLC-Sim 状态和现场/仿真事实，再按原任务的失败或未知结果流程处理。

## 工作流与预检

### 找不到工作流

- 清空搜索条件；
- 确认产品模式下该修订已经发布；
- 检查 Readiness 中的已加载数量是否与设备包检查报告一致；
- 设备包中有源码定义的流程，不一定已进入本次发布目录。

### Python 工作流导入冲突

导入用于创建新定义，同一工作流 UUID、节点 UUID 或作者函数名已存在时会拒绝，不会覆盖。为独立练习生成新 UUID；修改现有定义时使用其 Authoring draft/apply 流程或维护包内源文件。

### 导入时报动作或设备类型未知

确认设备类型使用绝对 import，规范 import package 中的 `@device` 已被 Catalog 静态扫描，启动图 `class` 能解析到该定义，并且运行中的 Workspace Catalog 是修改后的同一代。`package.yaml` 只登记工作流，不登记设备或资源；导入源码也不会执行 import 来“临时发现”类型。

### “新建工作流”没有打开编辑器

这是 Uni-Lab OS 页面的已知边界。使用“实验室操作”画布创建可复用操作，或从 Python/JSON 导入工作流。

### 预检返回 `invalid`

依次检查公开输入类型、必填值、设备绑定、子操作发布合同、`ResourceSlot`、来源站点重复和工作流诊断。修改定义后需要保存并重新发布。

### 预检返回 `temporarily_unavailable`

定义本身可能有效。检查设备在线状态、现有执行锁、物料位置、空闲站点、试剂数量预留和 Uni-Lab OS 排空状态。处理后重新预检。

### 预检通过但提交失败或进入等待

预检是零写入快照；另一个任务可能在你提交前占用了资源。以提交时返回和任务阻塞明细为准，不要重复创建任务。

### Debug API 返回 HTTP 410

旧 `/api/v1/debug/*` 已退役。创建标准 step Task，并在 `develop` 模式使用暂停、选择节点、执行下一步和继续。

## 任务与资源

### 第二个开发任务被拒绝

`develop` 只允许一个开发任务。结束现有任务，或在满足模式切换条件时切到 `product` 再创建并行任务。

### 任务长时间等待资源

打开节点和“阻塞与异常”，找到具体设备、物料、工位、库存或前置依赖。正常共享资源等待不需要人工释放。若 holder 对应已结束任务，再由管理员核对持久状态和现场后处理陈旧锁。

### 物料位置更新冲突

说明对象修订已经变化。刷新物料详情，确认是其他用户还是任务完成了移动，再基于最新位置操作。不要重复发送旧 revision。

### 没有可选择的试剂容器

目标物料必须使用带 `container` 标签的模板、尚未绑定试剂，并处于允许登记的状态。先到物料页核对容器和占用。

### 无法删除试剂或目录项

库存可能被任务预留，或目录项仍被库存引用。先查看消耗/预留和引用关系；不要删除正在被任务使用的数据。

## 设备和恢复

### 物料转移动作失败，现场位置与页面不一致

停止后继物理动作，现场确认真实站点，然后使用原任务的“物料转移结算”入口选择实际位置并填写原因。不要把物料手工移动到计划目标来掩盖失败。

### 节点显示 `execution_unknown`

不要重建任务或重发动作。检查机械臂/设备 journal、传感器和现场物体，完成只读对账后，在原任务解决未知结果。

### 强制解锁后设备仍在运行

强制解锁不会控制物理设备。立即按现场安全规程停机/急停，并禁止新任务派发；之后再对账 Job、物料和锁。

### 图像设备没有返回文件路径或算法结论

先核对设备动作合同：有些动作只表示触发成功，并不承诺返回文件或算法结论。不应通过反复执行解决接口能力缺失。

### 投料输出质量与秤读数理解不一致

先区分“目标/指令质量”和“传感器实测质量”。查看设备包定义的称量历史与最终秤结果，并按工艺容差单独判断。

## Trace 与日志

### 任务没有 Trace 链接

先确认 Readiness 是否配置 `traceUiUrl`，任务是否有 `trace_id`，追踪服务是否可达。Trace 上报 fail-open；没有 Trace 时仍要查看任务、Job、Uni-Lab OS 和设备日志。

### SSE 断开后状态不更新

任务事件是“需要重新读取”的通知，不是完整状态权威。重新加载 REST 详情；客户端也会使用轮询恢复。不要仅凭丢失的一条 SSE 判定任务没有变化。

## 提交问题时保留什么

- Uni-Lab OS 页面与发生时间；
- workflow/task/node/job UUID；
- 运行模式和发布修订；
- 输入、资源来源和预检结果；
- 设备在线状态、锁 holder 和内部设备会话；
- 错误 envelope 中的业务 `code` 与消息；
- Trace ID 及相关动作日志；
- 现场物料与设备状态，不包含密码、Token 或密钥。
