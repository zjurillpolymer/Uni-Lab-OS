# SZLab 临时调试模式部署

本目录用于把当前 Uni-Lab-OS 与 Uni-Lab-SZLab 源码组合成一个本地镜像，并在
Kubernetes `xiongyanfei` 命名空间中以临时调试模式运行。

该模式显式使用 `--control_plane local`，并按 Workbench 的正式本地拓扑拆成
两个进程：`workspace_backend` 提供 FastAPI、Inventory、Scheduler 和本地
Authority，`edge_runtime` 通过 `edge_control` 注册设备并加载 SZLab 驱动。
它们不会连接生产 Backend/Scheduler。Backend 的 `/runtime` 使用
`unilabos-local-debug-runtime` PVC，持久保存 Workflow、Inventory 和 Edge Authority
数据库；Edge 的 `/runtime` 仍使用 `emptyDir`，Pod 重建后本地协议恢复状态会重新
注册。Backend 的 SZLab 作者工作区单独使用
`unilabos-szlab-authoring-workspace` PVC，工作流 Python 源和
`workflow_publications.json` 可写并跨 Pod 重建保留；Edge 驱动运行目录仍为只读
镜像内容。

## 构建

在 Uni-Lab-OS 仓库根目录执行。构建使用两个固定提交的干净 detached
worktree，避免当前分支或未提交文件与镜像标签不一致：

```bash
set -euo pipefail

BUILD_ROOT="$(mktemp -d /home/xiongyanfei/.unilabos-szlab-build.XXXXXX)"
OS_SOURCE="$BUILD_ROOT/Uni-Lab-OS"
SZLAB_SOURCE="$BUILD_ROOT/Uni-Lab-SZLab"

cleanup_build_worktrees() {
  git worktree remove --force "$OS_SOURCE" >/dev/null 2>&1 || true
  git -C /home/xiongyanfei/Uni-Lab-SZLab \
    worktree remove --force "$SZLAB_SOURCE" >/dev/null 2>&1 || true
  rmdir "$BUILD_ROOT" >/dev/null 2>&1 || true
}
trap cleanup_build_worktrees EXIT

git worktree add --detach "$OS_SOURCE" \
  e237fb991c538e226198675accecbd7334571437
git -C /home/xiongyanfei/Uni-Lab-SZLab worktree add --detach "$SZLAB_SOURCE" \
  81215bcb23a61d191a9fa8072b176eda0f1dda92

test "$(git -C "$OS_SOURCE" rev-parse HEAD)" = \
  e237fb991c538e226198675accecbd7334571437
test -z "$(git -C "$OS_SOURCE" status --porcelain)"
test "$(git -C "$SZLAB_SOURCE" rev-parse HEAD)" = \
  81215bcb23a61d191a9fa8072b176eda0f1dda92
test -z "$(git -C "$SZLAB_SOURCE" status --porcelain)"

nerdctl -n k8s.io build \
  --build-context szlab="$SZLAB_SOURCE" \
  --build-arg OS_REVISION=e237fb991c538e226198675accecbd7334571437 \
  --build-arg SZLAB_REVISION=81215bcb23a61d191a9fa8072b176eda0f1dda92 \
  -f deploy/kubernetes-xiongyanfei/szlab-local-debug/Dockerfile \
  -t unilabos-szlab-local-debug:e237fb99-81215bcb-frontend-multipart-nomamba-otel \
  "$OS_SOURCE"
```

镜像标签中的两段短 SHA 分别对应 Uni-Lab-OS `e237fb99` 与 Uni-Lab-SZLab
`81215bcb`；该镜像同时包含内置 console 构建产物、`python-multipart` 和
OpenTelemetry OTLP/gRPC 导出依赖。构建前需确保节点已有
`uni-lab-demo-edge:trace-20260802-2`，Dockerfile 会从中复用已验证的 Python
3.11 OTel wheel 产物。

## 部署

以下清理命令会删除 `xiongyanfei` 命名空间内的所有资源和 PVC 数据。不得将
命名空间参数替换为其他值：

```bash
kubectl delete namespace xiongyanfei --wait=true
kubectl create namespace xiongyanfei
kubectl apply -f \
  /home/xiongyanfei/PLC-Sim/deploy/kubernetes-xiongyanfei/plc-sim.yaml
kubectl rollout status deployment/plc-sim -n xiongyanfei --timeout=5m
```

打开 `http://115.190.137.109:30160`，先在 GUI 中启动监听
`0.0.0.0:4855` 的 OPC UA Server，再用 `szlab` profile、`all` workflow 启动
SZLab Handshake Agent。GUI 状态确认两个进程均为 running 后再部署 Uni-Lab-OS：

```bash
if ! kubectl get secret unilabos-local-control -n xiongyanfei >/dev/null 2>&1; then
  kubectl create secret generic unilabos-local-control \
    -n xiongyanfei \
    --from-literal=api-key="$(openssl rand -hex 32)"
fi

kubectl apply -f deploy/kubernetes-xiongyanfei/szlab-local-debug/unilabos-local-debug.yaml
kubectl rollout status deployment/unilabos-local-debug -n xiongyanfei --timeout=10m
kubectl rollout status deployment/unilabos-local-edge -n xiongyanfei --timeout=10m
```

PVC 第一次挂载时，`seed-szlab-authoring-workspace` 初始化容器会从当前镜像复制
SZLab 领域包；检测到初始化标记后不会再次覆盖，以保护 UI 编辑和发布结果。升级
镜像中的 SZLab 基线时，应先导出或迁移该 PVC 中的作者数据，再进行受控更新，不能
直接用新镜像覆盖已有 Python 源。只有 `workspace_backend` 挂载这个可写工作区，
`edge_runtime` 不挂载它，继续以不可变镜像运行驱动。

按当前部署要求，FastAPI 通过 NodePort 直接暴露到公网：

```text
http://115.190.137.109:30183
```

该调试接口没有 TLS 和访问认证，只应在明确接受该风险的临时调试环境使用。

源码中的 `szlab-local-debug.json` 仍保留本地调试 URL。共享 ConfigMap 中的初始化
脚本会让两个 Deployment 等待 GUI 管理的 OPC UA Server 在 `plc-sim:4855` 就绪，
然后分别在 Pod 的 `emptyDir` 中生成 URL 为 `opc.tcp://plc-sim:4855` 的运行图，并将
该临时目录覆盖到工作区的 `deployment/graphs`；因此运行图仍位于 Uni-Lab-OS 允许
的工作区边界内。初始化脚本还会把机械臂的命令日志路径派生到可写的
`/runtime/edge/szlab_robot_commands.sqlite3`，使容器根文件系统可以保持只读。
该过程不会修改源码，也不引入 TCP proxy sidecar。

最终链路为：

```text
kernel-web -> unilabos-local-debug:18003 (workspace_backend)
           -> edge_control -> unilabos-local-edge (edge_runtime)
           -> Uni-Lab-SZLab szlab_poly_plc -> plc-sim:4855
```

`workspace_backend` 不加载实体驱动，只有 `edge_runtime` 会连接 PLC-Sim。PLC-Sim
未启动 Server 时两个进程会停留在初始化阶段，不会错误进入 Ready。
