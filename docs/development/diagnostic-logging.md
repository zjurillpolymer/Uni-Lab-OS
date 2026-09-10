# 诊断日志

设备继续正常采集和发现；默认省略逐次读取、无变化发现和成功健康轮询的记录。应用文件、Workbench 子进程输出和 ROS 原生输出均接入轮转与历史清理。

## 配置

在 `BasicConfig` 中配置，重启生效。也可以使用现有的 `UNILABOS_BASICCONFIG_<字段名大写>` 环境变量。

| 配置项 | 默认值 | 含义 |
| --- | --- | --- |
| `log_level` | `INFO` | Python 终端级别、ROS 原生级别 |
| `file_log_level` | `INFO` | 普通模式的 Python 文件级别 |
| `log_detailed` | `False` | 开启后生成正常采集/发现 TRACE，并将 Python 文件级别设为 TRACE |
| `log_max_bytes` | `52428800`（50 MiB） | 单文件轮转阈值 |
| `log_backup_count` | `9` | 每流备份数，另有一个当前文件，约 500 MiB/流 |
| `log_retention_days` | `7` | 已结束会话的历史文件保留期限 |
| `log_total_max_bytes` | `2147483648`（2 GiB） | 历史清理的总量目标 |
| `log_cleanup_interval_seconds` | `600` | 历史清理间隔 |

容量采用日志方案评论中扩大的建议。数值必须为正，容量和备份数必须为整数；非法配置会报错，不能通过设为 0 关闭容量控制。`log_detailed=False` 时，即使手工设置 TRACE 级别，也不生成正常逐次采集和发现记录。错误、上下线和任务事件保持原有行为。

Workbench 和 Managed Runtime 的输出接收器从启动环境读取同一组容量变量。它们不提前执行设备的 `local_config.py`；该文件中的配置只作用于加载它的应用日志。要统一整个 Workbench 的限制，应在启动 Workbench/Host 前设置环境变量，并重启 Host 和需要应用新策略的组件。例如：

```bash
export UNILABOS_BASICCONFIG_LOG_MAX_BYTES=52428800
export UNILABOS_BASICCONFIG_LOG_BACKUP_COUNT=9
export UNILABOS_BASICCONFIG_LOG_TOTAL_MAX_BYTES=2147483648
export UNILABOS_BASICCONFIG_LOG_DETAILED=false
```

## 文件与清理范围

每次启动使用含时间、PID、随机标识或既有启动代次的文件名，轮转段为 `.log.1`、`.log.2` 等。日志路径仍通过应用的 `[LOG_FILE]`、`[COMM_LOG_FILE]` 和 Workbench 的 `logPath` 返回。Workbench 查看日志时会跨最近几个轮转段读取，读取总量仍受接口限制。

| 输出 | 位置 |
| --- | --- |
| 应用主日志、通信日志 | `<working_dir>/logs/` |
| Workbench Host、backend、edge、PLC、renderer、模板校验输出 | `<workspace>/.unilabos/logs/workbench/` |
| Workbench 子应用自己的日志 | `.unilabos/runtime/workbench/.../logs/` |
| Managed Runtime Worker 输出 | `<working_dir>/logs/edge-<会话>.log` |
| 独立受管 PLC-Sim 输出 | Supervisor 状态目录中的 `simulator-<会话>.log` |
| 独立 ROS 原生输出 | `<working_dir>/logs/ros_console_<会话>.log` |

同一 `.unilabos` 或兼容目录 `unilabos_data` 下的诊断日志共用一个清理范围，包括嵌套的 Workbench 运行目录。显式独立工作目录的日志目录单独计算。独立受管 PLC-Sim 没有工作区身份，其 Supervisor 状态目录单独计算，不扫描模拟器源码或其他工作区。

写入者持有内核文件锁，进程退出后锁自动释放。清理器在启动、轮转后及定时检查时取得范围锁：先删超过保留期的已结束文件，再按最旧优先删到总量目标。活动会话的当前文件和备份计入总量，但历史清理不会删除它们；其备份数仍由自己的轮转器控制。

只处理本模块创建且标记有效的诊断 `.log` 文件。不会跟随软链接，也不接管审计、数据库、实验数据、操作幂等记录和工作站 POST 原始报送。工作站 GET 的失败记录写入应用诊断日志。没有占用标记的旧版日志保持原样；本次实现不自动迁移或删除这些文件。需要手动清理旧文件时，应先停止相关旧版进程并归档需要保留的记录。

2 GiB 是清理目标，不是磁盘硬配额。活动流较多、尚未执行清理、存在旧版日志，或 Python 单条记录超过阈值时，都可能超过该值。子进程字节流按阈值分块，超长无换行输出不会构造无界行缓冲。

## 进程与故障行为

业务进程仍由原 Host/Supervisor 直接启动，PID、进程组和收养逻辑保持一致。独立接收器读取 stdout/stderr；关闭或异常退出 Host 不会停止它。全部业务写端关闭后，接收器排空并退出。

接收器每块最多读取 64 KiB，磁盘队列最多约 4 MiB。磁盘写入失败时继续读取，保留会话锁，待恢复后记录累计丢弃字节数；队列过载会丢弃日志。结束时至多等待 5 秒排空，永久卡住的磁盘写入不会让接收器永远等待。接收器异常退出会向仍存活的管理进程报告。

强制杀死整个接收器会让业务写入收到 `EPIPE`/`BrokenPipeError`，测试验证了它不会永久等待管道；不能据此保证任意设备驱动都能继续运行。独立 ROS 的终端回显仍遵循原终端的背压行为。需要保留这两项运行限制，不能把日志接收器描述为无损或无故障组件。

ROS 的原生文件 sink 在受控接收器准备成功后禁用，console 和 `/rosout` 保留。原生级别与 Python 文件级别的区别及目标机验收见 [ROS 日志说明](ros-logging.md)。

## 验证

```bash
python -m pytest -q tests/utils/test_log_storage.py tests/utils/test_application_logging.py tests/utils/test_process_output.py tests/ros/test_logging_policy.py
python -m pytest -q tests/workspace_host tests/integration/test_managed_runtime_supervisor.py tests/integration/test_managed_runtime_supervisor_windows.py
```

测试覆盖轮转、跨文件尾读、占用锁、崩溃释放锁、期限与总量清理、旧文件和业务文件保护、INFO/TRACE 开关、OTel 重配、精确成功请求过滤、Host 退出后的持续输出与收养、磁盘失败及超长输出。

2026-09-09 的开发验证使用 macOS/Python 3.12。工作区广回归中的 11 项 Backend 模式/发布相关失败在基线 `17f0da914` 上同样存在。本机没有 ROS2 `rclpy`/`action_msgs`；真实 ROS 验收和依赖完整 ROS 的追踪测试需要目标环境。Windows 进程树测试也需 Windows 运行，不能以本机跳过代替通过。
