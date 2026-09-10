import base64
import importlib.util
import os
import traceback
from typing import Literal

from unilabos.utils import logger


class BasicConfig:
    ak = ""
    sk = ""
    working_dir = ""
    # 控制面固定由本站 OS 提供；Backend 上游模式已移除，不再建立远端连接。
    control_plane: Literal["local"] = "local"
    # OS 启动可见范围：develop 展示全部工作流定义，product 仅展示已发布普通工作流。
    # 该字段记录部署启动默认值；会话内热切换的权威值由 app.startup_mode 持有。
    startup_mode: Literal["develop", "product"] = "develop"
    # combined 保持历史单进程；Workbench 使用 workspace_backend + edge_runtime。
    process_role: Literal["combined", "workspace_backend", "edge_runtime"] = (
        "combined"
    )
    # 当前进程唯一允许发现/读取/写入的工作流源码（Workflow Source）选择目录。
    # 使用不可变 tuple，空值表示没有本地源码授权，禁止隐式扫描工作区。
    workflow_editable_package_roots: tuple[str, ...] = ()
    # 工作区包目录（PackageCatalog）已编译的工作流源码
    # （Workflow Source）发现计划；``None`` 时保留旧可编辑包根目录发现。
    workflow_source_discovery_plan: object | None = None
    # 与当前包目录编译代绑定的 Workbench 精确源码挂载；无工作区时保持 ``None``。
    workspace_package_mount_projection: object | None = None
    # 与当前包目录同代编译的只读物料外形和模型资产，供纯 Authoring Web 进程发布。
    workspace_material_shapes: tuple[dict[str, object], ...] = ()
    workspace_material_model_catalog: object | None = None
    config_path = ""
    is_host_mode = True
    # False（默认）：Slave 必须等 HostLink/Host ROS 服务就绪后才初始化 ROS。
    # True：显式离线降级，跳过首次 Host 等待及旧 ROS 注册，HostLink 仍后台重连。
    slave_no_host = False
    upload_registry = False
    machine_name = "undefined"
    vis_2d_enable = False
    no_update_feedback = False
    enable_resource_load = True
    # 本地模式不建立云端 WebSocket；跨进程动作通信由 edge_control 显式创建。
    communication_protocol = "local"
    startup_json_path = None  # 填写绝对路径
    disable_browser = False  # 禁止浏览器自动打开
    port = 8002  # 本地HTTP服务
    # 内置 React 控制台对外暴露时的浏览器边界；空白名单保持历史兼容，不启用
    # Host 限制。Docker Desktop Edge 部署会显式配置 loopback 与集群服务域名。
    frontend_allowed_hosts: str = ""
    frontend_same_origin: bool = False
    check_mode = False  # CI 检查模式，用于验证 registry 导入和文件一致性
    action_mode: Literal["real", "simulate"] = "real"  # 动作派发或模拟成功回执
    extra_resource = False  # 是否加载lab_开头的额外资源
    # 'TRACE', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        "INFO"
    )
    # 默认仅保留运行信息；显式启用详细日志时文件级别降至 TRACE。
    file_log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_detailed: bool = False
    log_max_bytes: int = 50 * 1024 * 1024
    log_backup_count: int = 9
    log_retention_days: float = 7
    log_total_max_bytes: int = 2 * 1024 * 1024 * 1024
    log_cleanup_interval_seconds: float = 600

    @classmethod
    def auth_secret(cls):
        if not cls.ak or not cls.sk:
            return ""
        target = f"{cls.ak}:{cls.sk}"
        base64_target = base64.b64encode(target.encode("utf-8")).decode("utf-8")
        return base64_target


# WebSocket配置
class WSConfig:
    reconnect_interval = 5  # 重连间隔（秒）
    max_reconnect_attempts = 999  # 最大重连次数
    # 注意：字段名带 ws_ 前缀，是为了让旧客户端遗留的 local_config 中旧字段(ping_interval/ping_timeout)失效，
    # 从而强制采用下面的新默认值。请勿改回旧名。
    ws_ping_interval = 5  # ping间隔（秒），对齐服务端 PingPeriod
    ws_ping_timeout = 8  # pong等待超时（秒），对齐服务端 PongWait


# 正式 Backend 控制面的 Edge 协议配置；仅 ``control_plane=backend`` 使用。
class EdgeControlConfig:
    api_key = ""
    # 动作进程访问远端 Backend 物料接口时使用；本地调度协议只用 api_key。
    backend_api_key = ""
    edge_key = ""
    instance_uuid = ""
    capability_revision = "unilabos-edge-v1"
    scheduler_addr = ""
    backend_addr = ""
    state_db = ""
    reconnect_interval = 5.0
    request_timeout = 10.0
    event_retry_interval = 5.0


# HTTP配置
class HTTPConfig:
    remote_addr = "https://leap-lab.bohrium.com/api/v1"
    # schedule 通道（WebSocket）地址；为空时从 remote_addr 派生：带端口则 +1，否则沿用原 netloc
    schedule_addr = ""
    # OS 物料查询固定使用当前主进程的本地库存权威；正式后端由前端直接选择。
    material_query_timeout = 10


# Host-Slave TCP 请求通路（HostLink）由 Edge 微后端拥有：负责连接生命周期、
# 在线监控、物料转发与 ROS 配置下发；HostNode 只提供运行时资源树兜底。
class HostLinkConfig:
    enable = True
    host = ""  # Slave 侧：Host 微后端 IP；空 = 不启用 TCP 通路，走旧 ROS 链路
    port = 7302  # 通路端口（host 监听 / slave 连接）
    bind = "0.0.0.0"  # host 侧监听地址
    advertise_ip = ""  # host 对外 IP（下发 slave 作 ROS 静态对端）；空 = 自动探测
    heartbeat_interval = 5  # slave ping 周期（秒）
    heartbeat_timeout = 15  # host 判离线阈值（秒）
    connect_timeout = 5  # 连接/握手超时（秒）
    request_timeout = 10  # 单请求超时（秒）
    # ROS 组网协助（host 经握手下发，slave 在 rclpy.init 前套用；空 = 沿用 host 环境变量）
    ros_assist_apply = (
        True  # slave 是否套用 host 下发的组网信息；False = 完全用本地环境
    )
    # （隔离场景/联网测试/手动管理组网时关闭：HostLink 照常连接，仅不动 ROS 环境）
    ros_domain_id = ""  # ROS_DOMAIN_ID
    ros_discovery_range = (
        ""  # SUBNET / LOCALHOST / OFF；OFF = 关闭组播自动发现（纯单播降级）
    )
    ros_static_peers = ""  # 分号分隔 ip 列表；空 = 自动用 advertise_ip
    # 空 = Host 微后端自动启动 Fast DDS Discovery Server；off = 禁用；
    # ip:port = 使用外部 Server，不由本进程管理。
    ros_discovery_server = ""
    # 0 = 复用 HostLink 的数字端口（HostLink/TCP + Fast DDS/UDP）；非零可分开指定。
    ros_discovery_port = 0


# OpenTelemetry/SigNoz（默认关闭；仅显式开启时加载可选 SDK）。
# 环境变量既可走配置映射（UNILABOS_OTELCONFIG_*），也支持标准 OTEL_*；
# 标准变量优先级更高，见 unilabos.utils.tracing.TracingSettings。
class OTelConfig:
    enabled = False
    endpoint = ""  # OTLP/gRPC，例如 http://127.0.0.1:4317
    protocol = "grpc"  # grpc 或 http/protobuf
    logs_enabled = True  # 启用 tracing 后默认同时导出 Python logging
    logs_endpoint = ""  # 空值复用 endpoint
    logs_protocol = ""  # 空值复用 protocol
    insecure = True
    service_name = "uni-lab-edge"  # 对齐云端 uni-lab-http / uni-lab-scheduler
    service_namespace = "unilab"
    service_version = "0.11.4"
    deployment_environment = ""
    headers = ""  # 逗号分隔 key=value；不得写入日志
    resource_attributes = ""  # 逗号分隔 key=value；敏感键会被过滤
    trace_sampler = "parentbased_always_on"
    sample_ratio = 1.0
    max_queue_size = 2048
    max_export_batch_size = 512
    schedule_delay_ms = 5000
    export_timeout_ms = 5000
    shutdown_timeout_ms = 5000


# ROS配置
class ROSConfig:
    modules = [
        "std_msgs.msg",
        "geometry_msgs.msg",
        "control_msgs.msg",
        "control_msgs.action",
        "nav2_msgs.action",
        "unilabos_msgs.msg",
        "unilabos_msgs.action",
    ]


def _update_config_from_module(module):
    for name, obj in globals().items():
        if isinstance(obj, type) and name.endswith("Config"):
            if hasattr(module, name) and isinstance(getattr(module, name), type):
                for attr in dir(getattr(module, name)):
                    if not attr.startswith("_"):
                        setattr(obj, attr, getattr(getattr(module, name), attr))


_LOG_CONFIG_FIELDS = frozenset({
    "log_level", "file_log_level", "log_detailed", "log_max_bytes",
    "log_backup_count", "log_retention_days", "log_total_max_bytes",
    "log_cleanup_interval_seconds",
})


def _update_config_from_env():
    prefix = "UNILABOS_"
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        try:
            key_path = env_key[len(prefix) :]  # Remove UNILAB_ prefix
            class_field = key_path.upper().split("_", 1)
            if len(class_field) != 2:
                logger.warning(f"[ENV] 环境变量格式不正确：{env_key}")
                continue

            class_key, field_key = class_field
            # 遍历 globals 找匹配类（不区分大小写）
            matched_cls = None
            for name, obj in globals().items():
                if name.upper() == class_key and isinstance(obj, type):
                    matched_cls = obj
                    break

            if matched_cls is None:
                logger.warning(f"[ENV] 未找到类：{class_key}")
                continue

            # 查找类属性（不区分大小写）
            matched_field = None
            for attr in dir(matched_cls):
                if attr.upper() == field_key:
                    matched_field = attr
                    break

            if matched_field is None:
                logger.warning(
                    f"[ENV] 类 {matched_cls.__name__} 中未找到字段：{field_key}"
                )
                continue

            current_value = getattr(matched_cls, matched_field)
            attr_type = type(current_value)
            if matched_cls is BasicConfig and matched_field in {"log_retention_days", "log_cleanup_interval_seconds"}:
                value = float(env_value)
            elif matched_cls is BasicConfig and matched_field in {"log_max_bytes", "log_backup_count", "log_total_max_bytes"}:
                value = int(env_value)
            elif matched_cls is BasicConfig and matched_field == "log_detailed":
                normalized = env_value.lower()
                if normalized not in {"true", "1", "yes", "false", "0", "no"}:
                    raise ValueError("log_detailed 必须为 true/false、1/0 或 yes/no")
                value = normalized in {"true", "1", "yes"}
            elif attr_type == bool:
                value = env_value.lower() in ("true", "1", "yes")
            elif attr_type == int:
                value = int(env_value)
            elif attr_type == float:
                value = float(env_value)
            else:
                value = env_value
            setattr(matched_cls, matched_field, value)
            field_name = matched_field.lower()
            sensitive = any(
                marker in field_name
                for marker in ("secret", "token", "password", "api_key", "headers")
            ) or field_name in {"ak", "sk"}
            display_value = "***" if sensitive and str(value) else value
            logger.info(
                f"[ENV] 设置 {matched_cls.__name__}.{matched_field} = {display_value}"
            )
        except Exception as e:
            if env_key.upper() in {
                f"UNILABOS_BASICCONFIG_{field.upper()}" for field in _LOG_CONFIG_FIELDS
            }:
                raise ValueError(f"日志配置环境变量 {env_key} 无效: {e}") from e
            logger.warning(f"[ENV] 解析环境变量 {env_key} 失败: {e}")


def _validate_log_config() -> None:
    """日志配置错误不得静默回退为无限增长或错误的诊断模式。"""
    from unilabos.utils.log import _logging_settings
    from unilabos.utils.log_storage import LogPolicy

    policy = LogPolicy.from_config(BasicConfig)
    _logging_settings(BasicConfig.log_level, BasicConfig.file_log_level, BasicConfig.log_detailed, policy)


def load_config(config_path=None):
    # 如果提供了配置文件路径，从该文件导入配置
    if config_path:
        env_config_path = os.environ.get("UNILABOS_BASICCONFIG_CONFIG_PATH")
        config_path = env_config_path if env_config_path else config_path
        BasicConfig.config_path = os.path.abspath(os.path.dirname(config_path))
        if not os.path.exists(config_path):
            logger.error(f"[ENV] 配置文件 {config_path} 不存在")
            exit(1)
        try:
            module_name = "lab_" + os.path.basename(config_path).replace(".py", "")
            spec = importlib.util.spec_from_file_location(module_name, config_path)
            if spec is None:
                logger.error(f"[ENV] 配置文件 {config_path} 错误")
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore
            _update_config_from_module(module)
            logger.info(f"[ENV] 配置文件 {config_path} 加载成功")
            _update_config_from_env()
            _validate_log_config()
        except Exception:
            logger.error(f"[ENV] 加载配置文件 {config_path} 失败")
            traceback.print_exc()
            exit(1)
    else:
        config_path = os.path.join(os.path.dirname(__file__), "example_config.py")
        load_config(config_path)
