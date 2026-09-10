"""Publish LLM-friendly Markdown alongside the HTML product manual."""

from __future__ import annotations

import html
import posixpath
import shutil
from pathlib import Path
from typing import Any


_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "认识与快速上手",
        (
            "index",
            "overview",
            "console",
        ),
    ),
    (
        "系统安装与配置",
        (
            "installation",
            "environment",
            "interfaces",
        ),
    ),
    (
        "设备包开发规范",
        (
            "unilabos-installation",
            "repository-builder-skill",
            "scenario-guide",
            "workspace",
            "device-template",
            "template-library",
            "device-registration",
            "generic-device",
            "plc-station",
            "serial-network",
            "host-api",
            "mouse-automation",
            "stack",
            "material-template",
            "deck-warehouse",
            "plate-tiprack",
            "container-template",
            "vial-rack",
            "magazine",
            "sheet-battery",
            "material-state",
            "other-materials",
            "startup-files",
            "graph-json",
            "workflow",
            "experiment-operations",
            "complete-workflow",
            "ai-workflow-authoring",
        ),
    ),
    (
        "环境、部署、运行",
        (
            "deployment",
            "runtime-safety",
            "workflows",
        ),
    ),
    (
        "排查与参考",
        (
            "troubleshooting",
            "api-reference",
        ),
    ),
)


_DESCRIPTIONS: dict[str, str] = {
    "index": "说明书入口、学习路线、能力状态标签和已部署产品链接。",
    "overview": "产品模型、适用角色、核心对象和当前部署边界。",
    "installation": "先安装 Uni-Lab OS，再下载示例设备包并以 dry-run 启动。",
    "environment": "Conda 环境、Workspace 文件、启动图（Graph JSON）、本地配置以及运行与启动模式。",
    "console": "浏览 Uni-Lab OS 页面，并了解各入口的当前功能和限制。",
    "interfaces": "了解开发工具、接口入口、适用场景和能力边界。",
    "unilabos-installation": "按工作区、设备、物料、启动图和工作流的顺序完成设备包开发与系统启动。",
    "repository-builder-skill": "使用仓库内的 AI Skill 新建、迁移、修改或诊断用户自己的设备包。",
    "workspace": "规划设备包目录、文件职责、命名规则和交付检查。",
    "device-template": "根据控制方式选择设备接入模板，并完成设备合同和验证。",
    "template-library": "按设备能力选择类别、动作和模拟实现，不依赖固定类别数量。",
    "device-registration": "登记设备、动作参数和状态，并验证页面表单与设备联动。",
    "generic-device": "定义所有设备共同遵守的身份、配置、动作、状态和错误规范。",
    "plc-station": "把 PLC 点位和握手过程封装成业务动作，并完成仿真与真机验收。",
    "serial-network": "接入串口、TCP 或 Modbus 设备，并规范超时、重连和报文处理。",
    "host-api": "把上位机 HTTP 或 SDK 能力封装成稳定、可校验的设备动作。",
    "mouse-automation": "在缺少正式接口时受控接入界面自动化，并明确安全限制。",
    "material-template": "定义设备包中的物料类型、属性、放置规则、状态和工作流合同。",
    "stack": "光电与旋转堆栈必须同时定义物料树和设备能力；光电设备面尚无统一规范，旋转堆栈按标准动作接入。",
    "deck-warehouse": "定义工作站台面、仓库、普通堆栈/料架和放置位的坐标、占用与兼容约束。",
    "plate-tiprack": "定义孔板和吸头盒的规格、孔位、容量、方向与状态。",
    "container-template": "定义通用容器的容量、内容物、封闭状态和放置兼容性。",
    "vial-rack": "定义小瓶载架及其槽位、编号、方向和小瓶兼容规则。",
    "magazine": "定义弹夹的层位、装载顺序、容量和空满状态。",
    "sheet-battery": "定义片状物料与组装成品的身份、工序状态和装配关系。",
    "material-state": "规范物料条码、内容物、位置、数量和状态更新。",
    "other-materials": "按通用约束接入袋、盒、工具等其他可追踪物料。",
    "startup-files": "准备不同环境使用的启动图文件，并完成加载前检查。",
    "graph-json": "逐项编写启动图中的设备、资源、放置位、连接配置和实例关系。",
    "workflow": "按统一规范编写实验操作和完整工作流，并完成登记、预检和验收。",
    "experiment-operations": "编写职责单一、可发布和可复用的实验操作。",
    "complete-workflow": "组合设备动作、实验操作和物料流，形成完整实验流程。",
    "ai-workflow-authoring": "让 AI 基于当前设备包证据生成工作流，并由人审查、导入、发布和验证。",
    "workflows": "管理工作流定义、修订、发布、预检和任务运行。",
    "scenario-guide": "按设备、物料、工作流和现场约束验收用户设备包。",
    "runtime-safety": "dry-run 与真实动作、develop 与 product 模式、联锁和恢复规则。",
    "deployment": "把已验收的 Workspace 和 Uni-Lab OS 部署到 Kubernetes，并验证、升级或回滚。",
    "troubleshooting": "按症状排查安装、创作、调度、设备连接、物料和任务问题。",
    "api-reference": "常用 HTTP 接口、请求合同、状态语义和安全调用方式。",
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

    # Every generated HTML page keeps a working Markdown alternate, while the
    # machine-readable directory and full manual include only visible navigation.
    for docname in sorted(found_docs):
        source = source_root / f"{docname}.md"
        if not source.is_file():
            continue
        target = output_root / f"{docname}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if docname in ordered_docs:
            sources[docname] = source.read_text(encoding="utf-8")

    index_lines = [
        "# Uni-Lab OS 产品使用说明书",
        "",
        "> 帮助新用户安装 Uni-Lab OS、开发设备包，并安全地预检和运行实验任务。",
        "",
        "从零使用时，按“系统安装与配置”“设备包开发规范”“环境、部署、运行”的顺序阅读；遇到问题时进入“排查与参考”。",
        "",
    ]
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
