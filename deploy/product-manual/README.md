# Uni-Lab OS 产品说明书部署

本目录只构建 `docs/product_manual/`，并将静态站点部署到指定的 Kubernetes
命名空间。它不会修改 Uni-Lab OS Runtime、Edge、PLC-Sim 或 SigNoZ。

## 构建

在 `Uni-Lab-OS` 仓库根目录运行：

```bash
export DOCS_DEPLOY_DIR="deploy/product-manual"
nerdctl -n k8s.io build \
  -f "$DOCS_DEPLOY_DIR/docs.Dockerfile" \
  -t unilabos-docs:product-manual-20260907-v14 .
```

该集群为单节点，Deployment 从本机 containerd 的 `k8s.io` namespace 读取镜像，
因此清单使用 `imagePullPolicy: Never`。

## 部署

```bash
export TARGET_NAMESPACE="unilabos-demo"
kubectl -n "$TARGET_NAMESPACE" apply \
  -f "$DOCS_DEPLOY_DIR/unilabos-docs.yaml"
kubectl rollout status deployment/unilabos-docs \
  -n "$TARGET_NAMESPACE" --timeout=5m
```

公网地址为 `http://115.190.137.109:30184/`。

面向 AI 的静态入口：

- `/llms.txt`：按主题整理的全站 Markdown 导航；
- `/llms-full.txt`：按推荐顺序合并的整本说明书；
- `/<页面名>.md`：与每个 HTML 页面对应的原始 Markdown。

若需要回滚，使用：

```bash
kubectl rollout undo deployment/unilabos-docs -n "$TARGET_NAMESPACE"
```

当前入口是明文 HTTP NodePort，仅适合授权演示。生产环境应在该 Service 前增加 TLS、
身份认证和访问控制。
