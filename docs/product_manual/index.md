# Uni-Lab OS 产品使用说明书

产品定位、业务能力和核心对象统一见[认识 Uni-Lab OS](overview.md)。本页只用于选择适合当前任务的阅读入口。

<div class="manual-meta">
适用环境：通用安装与接入场景　·　手册版本：2026.09.08　·　设备包可在安装 OS 后创建
</div>

<div class="entry-links">
<p><strong>Uni-Lab OS 入口</strong>：安装完成后运行 <code>unilab workspace status --json</code>，从实际输出取得页面和 API 地址。</p>
</div>

:::{warning}
不要把本地开发端口直接暴露到公网。生产部署应在入口前配置 TLS、身份认证、授权和网络访问控制，并通过密钥系统提供凭证。
:::

## 从哪里开始

- **已有可用环境**：先读[认识产品](overview.md)，再进入[Uni-Lab OS 快速上手](console.md)。
- **从零建设环境**：先完成[系统安装](installation.md)，再下载并启动[示例设备包](demo-lab.md)，最后按[设备包规范与系统启动](unilabos-installation.md)替换为真实设备。
- **编写设备包**：在[设备包规范与系统启动](unilabos-installation.md)中依次完成工作区、设备、物料、启动图和工作流。
- **发布并运行**：进入[工作流发布与任务运行](workflows.md)，生产上线前完成[运行模式、安全与恢复](runtime-safety.md)和[Kubernetes 部署](deployment.md)。
- **验收与排查**：使用[设备包验收](scenario-guide.md)、[故障排查](troubleshooting.md)和[API 使用参考](api-reference.md)。

## 本手册如何描述能力

同一功能在源码、控制台和线上环境中可能处于不同阶段。本手册统一使用以下状态：

| 状态 | 含义 |
| --- | --- |
| <span class="status status-ready">当前可用</span> | 本次安装已加载、连接并完成对应验收。 |
| <span class="status status-config">需要配置</span> | 代码已实现，但依赖设备、凭证、联网服务或运行模式。 |
| <span class="status status-limited">当前受限</span> | 只有 API 或开发工具支持，Uni-Lab OS 页面没有入口，或能力有明确限制。 |
| <span class="status status-unavailable">当前不可用</span> | 接口已退役、执行器未启用，或界面只是占位。 |
| <span class="status status-experimental">实验验证</span> | 只在隔离测试中验证，尚未批准用于生产。 |

“源码已定义”不等于“当前线上已发布”，而“仿真通过”也不等于“真机已完成安全验收”。各页会明确说明这些边界。

```{toctree}
:caption: 认识与快速上手
:maxdepth: 1

overview
console
示例设备包 <demo-lab>
```

```{toctree}
:caption: 系统安装与配置
:maxdepth: 1

installation
environment
```

```{toctree}
:caption: 设备包开发规范
:maxdepth: 2

unilabos-installation
使用 AI 设备包生成器（实验性） <repository-builder-skill>
scenario-guide
```

```{toctree}
:caption: 环境、部署、运行
:maxdepth: 1

deployment
runtime-safety
workflows
```

```{toctree}
:caption: 参考
:maxdepth: 1

troubleshooting
api-reference
```
