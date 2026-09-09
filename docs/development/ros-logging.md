# ROS 原生日志容量

UniLabOS 的 Host/Slave ROS 入口在 `rclpy.init` 前准备原生日志接收路径。相机、关节转发器、doctor 诊断，以及 Rviz/Laiyu 液体处理后端首次创建 ROS context 的独立入口也调用同一准备函数；已有 context 仍由其原有调用方管理。硬件驱动文件中的独立调试演示不在产品日志接管范围内。

- Workbench 已将业务进程的 stderr 指向独立日志接收器时，通过管道身份标记验证并复用该接收器。
- 若平台不提供可靠的管道身份（如部分 Windows 匿名管道），会额外创建受限 tee，不根据相同的零值身份跳过磁盘接收。
- 独立启动时，fd 2 接入独立接收器，写入 `<working_dir>/logs/ros_console_<时间>-<PID>-<随机标识>.log`，同时回显原 stderr。真正来自 C/C++ 的输出也经过该路径。
- ROS 参数强制启用 console、禁用原生 external-library 磁盘日志。`/rosout` 保留 ROS 自身实现及调用方的显式配置。这样不会再由默认 spdlog sink 另外生成无容量限制的日志。
- 接收器未成功准备时，ROS 初始化报错；首次尝试接管已由外部代码初始化的 context 也报错，避免假定原来的 spdlog sink 已关闭。进程内正常重启先关闭 ROS，再恢复 stderr、排空接收器。

原生 ROS 日志默认 INFO，跟随 `BasicConfig.log_level`；TRACE 对应 ROS DEBUG，CRITICAL 对应 FATAL。原生 severity 在 console、磁盘接收和 `/rosout` 之前过滤，因此 `file_log_level` 或 `log_detailed` 不能单独启用原生 DEBUG。如需原生 DEBUG，应显式设置 `log_level=DEBUG` 或传入 ROS 的 `--log-level`。Python 文件日志仍可独立配置。

原生 console 固定使用 `RCUTILS_LOGGING_USE_STDOUT=0`。这个值必须在 rcutils 首次初始化前设置；UniLabOS 主启动流程识别 ROS 后端后、导入注册表前设置，Host/Slave 直接入口也在导入 rclpy 前设置。嵌入第三方程序时，应在第一次使用 rclpy 日志前调用 `prepare_ros_logging` 并将其返回参数传给 `rclpy.init`。

接收器使用统一 `LogPolicy`：默认每段 50 MiB、9 个备份、7 天保留和总量 2 GiB；工作区内各运行目录共享清理范围。历史清理尊重当前仍占用文件的会话锁。策略细节见[诊断日志](diagnostic-logging.md)。独立 fd 2 接收器还会保存写到同一 stderr 的 Python console 输出，因此某些行也会出现在 Python 应用日志内。

磁盘慢或故障时，接收器的有界队列限制内存占用；过载会产生丢弃字节数告警，磁盘恢复后也会记录累计丢失。独立启动时，原 stderr 回显与磁盘队列分开，仍保持原有终端的背压行为。强制杀死接收器、终端永久阻塞和磁盘不可写都不构成无损保证；`/rosout` 是独立的 ROS 输出路径。

## 验收

本次开发环境没有安装 ROS。已通过不依赖 ROS 的行为测试，包括直接调用 libc 向 fd 2 输出、所有记录回显、文件轮转、最后一条 ERROR 落盘、初始化失败恢复 stderr 和重启清理。它们不能替代目标 ROS 发行版上的验收。

在已 source ROS 环境并安装 UniLabOS 的机器执行：

```bash
python -m pytest -q tests/ros/test_logging_policy.py
python -m unilabos.ros.logging_acceptance --working-dir /tmp/ros-log-check
```

第二条命令不连接实验设备，使用独立测试节点和默认域号 213（可通过 `--domain-id` 修改），创建临时子目录并将段容量临时降为 32 KiB、2 个备份。它直接调用目标 ROS 的 C `rcutils_log`，验证可变参数格式化的 ERROR 同时进入 `/rosout` 和受限文件，并检查 INFO、轮转和原生无界日志文件缺席。终端应看到 INFO 和最终 ERROR；末尾 JSON 各项必须为 `true` 且退出码为 0。输出目录保留供检查。

设计依据为 ROS 2 官方的[日志配置说明](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Logging.html)和 [Humble spdlog 实现](https://github.com/ros2/rcl_logging/blob/humble/rcl_logging_spdlog/src/rcl_logging_spdlog.cpp)：该实现使用普通文件 sink，不能把 `--log-config-file` 视作已支持的轮转配置。
