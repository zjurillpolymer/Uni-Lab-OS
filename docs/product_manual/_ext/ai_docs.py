"""Publish LLM-friendly Markdown alongside the HTML product manual."""

from __future__ import annotations

import html
import posixpath
import shutil
from pathlib import Path
from typing import Any


_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "认识与快速体验",
        (
            "index",
            "overview",
            "console",
            "quickstart",
        ),
    ),
    (
        "安装与实验室开发",
        (
            "installation",
            "environment",
            "workflow-concepts",
            "lab-repository",
            "devices",
            "interfaces",
            "repository-builder-skill",
        ),
    ),
    (
        "工作流创作",
        (
            "first-workflow",
            "materials",
            "reagents",
            "workflow-features",
            "operations",
            "ai-workflow-authoring",
        ),
    ),
    (
        "部署与运行",
        (
            "runtime-safety",
            "plc-sim",
            "deployment",
            "workflows",
            "tasks",
        ),
    ),
    (
        "SZLab 场景",
        (
            "szlab",
        ),
    ),
    (
        "排障与参考",
        (
            "troubleshooting",
            "capability-matrix",
            "api-reference",
            "evidence",
        ),
    ),
)


_DESCRIPTIONS: dict[str, str] = {
    "index": "说明书入口、学习路线、能力状态标签和已部署产品链接。",
    "overview": "产品模型、适用角色、核心对象和当前部署边界。",
    "installation": "安装 Uni-Lab OS 与 SZLab、构建 Console、启动 dry-run 并验收就绪状态。",
    "environment": "Conda 环境、Workspace 文件、Graph、本地配置以及运行与启动模式。",
    "quickstart": "在已部署演示环境中运行一个安全的现有工作流。",
    "console": "浏览 Console 页面，并了解各入口的当前功能和限制。",
    "lab-repository": "从零建立实验室领域仓库，定义设备、Graph 和工作流，并让 Backend 与 Edge 加载。",
    "repository-builder-skill": "在本地 Workbench 中使用实验性 Agent Skill 新建、迁移或诊断领域仓库，并完成人工验收。",
    "workflow-concepts": "静态 DSL、DAG、Workflow/Node/Task/Job、设备选择器、合同和修订。",
    "ai-workflow-authoring": "推荐的代码取证型 AI 创作流程、提示词、人工审查和安全关卡。",
    "first-workflow": "创建、导入、发布、预检并 dry-run 一个最小 SZLab 控制流工作流。",
    "workflow-features": "类型输入、控制流、并行、资源、物料、数量合同和子工作流。",
    "workflows": "管理定义、修订、发布、预检、普通运行和单步运行。",
    "operations": "创建和复用实验操作，并理解组合工作流边界。",
    "tasks": "观察 Task 与 Job、调度、资源等待、控制命令、失败和恢复。",
    "materials": "管理 PLR 物料资源、站点、保管、转运和库存一致性。",
    "reagents": "管理试剂身份、库存、数量、历史以及不同客户端的能力差异。",
    "devices": "理解设备目录、Edge 连接、动作、模式和安全限制。",
    "plc-sim": "打开 PLC-Sim Web GUI，核对 OPC UA、SZLab 握手代理和 Edge 会话，并配置本地仿真。",
    "szlab": "SZLab 部署、工位、已登记工作流、示例和已知边界。",
    "runtime-safety": "dry-run 与真实动作、develop 与 product 模式、联锁和恢复规则。",
    "deployment": "把已验收的 Workspace、Backend、Edge 与 Console 部署到 Kubernetes，并验证、升级或回滚。",
    "troubleshooting": "按症状排查安装、创作、调度、Edge、物料和任务问题。",
    "capability-matrix": "以代码与目标环境验证为依据的产品能力状态。",
    "interfaces": "Console、Workbench、CLI、MCP、Backend 和仿真器的精确能力边界。",
    "api-reference": "常用 HTTP 接口、请求合同、状态语义和安全调用方式。",
    "evidence": "说明书采用的源码、部署检查和事实判定规则。",
}


_TOOLBAR = """
<div class="ai-docs-toolbar" data-ai-docs-toolbar
     data-markdown-url="{markdown_url}"
     data-llms-url="{llms_url}"
     data-llms-full-url="{llms_full_url}">
  <div class="ai-docs-menu-shell">
    <div class="ai-docs-split">
      <button class="ai-docs-copy-primary" type="button" data-ai-docs-copy
              aria-disabled="true" disabled>
        <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16">
          <path d="M9 5h6m-6 4h6m-6 4h4M8 3h8a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/>
        </svg>
        <span data-ai-docs-trigger-label>复制页面</span>
      </button>
      <button class="ai-docs-trigger" type="button" aria-expanded="false"
              aria-controls="ai-docs-menu-{menu_id}" aria-label="打开 AI 文档菜单">
        <svg class="ai-docs-chevron" aria-hidden="true" viewBox="0 0 24 24" width="14" height="14">
          <path d="m7 10 5 5 5-5"/>
        </svg>
      </button>
    </div>
    <div class="ai-docs-popover" id="ai-docs-menu-{menu_id}" hidden>
      <button class="ai-docs-menu-item" type="button" data-ai-docs-copy
              aria-disabled="true" disabled>
        <span class="ai-docs-item-icon" aria-hidden="true">⧉</span>
        <span><strong>复制页面</strong><small data-ai-docs-copy-help>正在准备本页 Markdown</small></span>
      </button>
      <a class="ai-docs-menu-item" href="{markdown_url}" target="_blank" rel="noopener noreferrer">
        <span class="ai-docs-item-icon" aria-hidden="true">M↓</span>
        <span><strong>以 Markdown 格式查看 <span aria-hidden="true">↗</span></strong><small>打开本页纯文本版本</small></span>
      </a>
      <a class="ai-docs-menu-item" href="{llms_url}" target="_blank" rel="noopener noreferrer">
        <span class="ai-docs-item-icon" aria-hidden="true">AI</span>
        <span><strong>LLMs.txt <span aria-hidden="true">↗</span></strong><small>让 AI 按主题发现全部文档</small></span>
      </a>
      <a class="ai-docs-menu-item" href="{llms_full_url}" target="_blank" rel="noopener noreferrer">
        <span class="ai-docs-item-icon" aria-hidden="true">≡</span>
        <span><strong>LLMs-full.txt <span aria-hidden="true">↗</span></strong><small>获取整本说明书的 Markdown</small></span>
      </a>
    </div>
  </div>
  <span class="ai-docs-status" role="status" aria-live="polite"></span>
</div>
"""


def _relative_targets(app: Any, pagename: str) -> tuple[str, str, str]:
    """Return Markdown, llms.txt, and llms-full.txt URLs relative to one page."""

    target_uri = app.builder.get_target_uri(pagename)
    target_dir = posixpath.dirname(target_uri) or "."
    markdown = posixpath.relpath(f"{pagename}.md", target_dir)
    llms = posixpath.relpath("llms.txt", target_dir)
    llms_full = posixpath.relpath("llms-full.txt", target_dir)
    return markdown, llms, llms_full


def _add_page_tools(
    app: Any,
    pagename: str,
    templatename: str,
    context: dict[str, Any],
    doctree: Any,
) -> None:
    """Add the toolbar and machine-discovery links to documentation pages."""

    del templatename, doctree
    if app.builder.format != "html" or pagename not in app.env.found_docs:
        return

    markdown, llms, llms_full = _relative_targets(app, pagename)
    escaped_markdown = html.escape(markdown, quote=True)
    escaped_llms = html.escape(llms, quote=True)
    escaped_full = html.escape(llms_full, quote=True)
    context["body"] = _TOOLBAR.format(
        markdown_url=escaped_markdown,
        llms_url=escaped_llms,
        llms_full_url=escaped_full,
        menu_id=html.escape(pagename.replace("/", "-"), quote=True),
    ) + str(context.get("body") or "")
    context["metatags"] = str(context.get("metatags") or "") + (
        f'<link rel="alternate" type="text/markdown" href="{escaped_markdown}">\n'
        f'<link rel="describedby" type="text/plain" href="{escaped_llms}">\n'
    )


def _title(source: str, fallback: str) -> str:
    for line in source.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _absolute_url(app: Any, path: str) -> str:
    base_url = str(app.config.html_baseurl or "").rstrip("/")
    return f"{base_url}/{path}" if base_url else f"/{path}"


def _ordered_documents(found_docs: set[str]) -> list[str]:
    ordered: list[str] = []
    for _, names in _SECTIONS:
        ordered.extend(name for name in names if name in found_docs)
    ordered.extend(sorted(found_docs.difference(ordered)))
    return ordered


def _write_machine_docs(app: Any, exception: Exception | None) -> None:
    """Copy source Markdown and generate compact/full LLM entry points."""

    if exception is not None or app.builder.format != "html":
        return

    source_root = Path(app.srcdir)
    output_root = Path(app.outdir)
    found_docs = set(app.env.found_docs)
    ordered_docs = _ordered_documents(found_docs)
    sources: dict[str, str] = {}

    for docname in ordered_docs:
        source = source_root / f"{docname}.md"
        if not source.is_file():
            continue
        target = output_root / f"{docname}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        sources[docname] = source.read_text(encoding="utf-8")

    index_lines = [
        "# Uni-Lab OS 产品使用说明书",
        "",
        "> Uni-Lab OS 的代码事实型产品手册：帮助新用户安装产品、用 AI 或手工编写工作流、理解编排特性，并安全地预检和运行任务。",
        "",
        "从零使用时，按“安装与实验室开发”“工作流创作”“部署与运行”的顺序阅读；SZLab 部署需先准备 PLC-Sim。代码实现与文档冲突时，以手册标注的当前源码事实和目标部署检查为准。",
        "",
    ]
    listed: set[str] = set()
    for heading, names in _SECTIONS:
        available = [name for name in names if name in sources]
        if not available:
            continue
        index_lines.extend((f"## {heading}", ""))
        for docname in available:
            title = _title(sources[docname], docname)
            description = _DESCRIPTIONS.get(docname, "Uni-Lab OS 产品说明书页面。")
            index_lines.append(
                f"- [{title}]({_absolute_url(app, f'{docname}.md')}): {description}"
            )
            listed.add(docname)
        index_lines.append("")

    extras = [name for name in ordered_docs if name in sources and name not in listed]
    if extras:
        index_lines.extend(("## 其他页面", ""))
        for docname in extras:
            title = _title(sources[docname], docname)
            index_lines.append(
                f"- [{title}]({_absolute_url(app, f'{docname}.md')}): "
                f"{_DESCRIPTIONS.get(docname, '其他产品说明书页面。')}"
            )
        index_lines.append("")
    index_lines.extend(
        (
            "## 完整内容",
            "",
            f"- [整本说明书]({_absolute_url(app, 'llms-full.txt')}): "
            "按推荐阅读顺序合并的全部说明书页面。",
            "",
        )
    )
    (output_root / "llms.txt").write_text("\n".join(index_lines), encoding="utf-8")

    full_lines = [
        "# Uni-Lab OS 产品使用说明书 — 完整 Markdown",
        "",
        "> 本文件按推荐阅读顺序合并整本产品手册；每节都标出原始 Markdown 地址。",
        "",
    ]
    for docname in ordered_docs:
        source = sources.get(docname)
        if source is None:
            continue
        full_lines.extend(
            (
                "---",
                "",
                f"Source: {_absolute_url(app, f'{docname}.md')}",
                "",
                source.rstrip(),
                "",
            )
        )
    (output_root / "llms-full.txt").write_text(
        "\n".join(full_lines), encoding="utf-8"
    )


def setup(app: Any) -> dict[str, Any]:
    app.connect("html-page-context", _add_page_tools)
    app.connect("build-finished", _write_machine_docs)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
