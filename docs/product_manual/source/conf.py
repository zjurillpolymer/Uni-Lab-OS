"""Sphinx configuration for the Uni-Lab OS product user manual."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent / "_ext"))

project = "Uni-Lab OS 产品使用说明书"
author = "Uni-Lab"
copyright = "2026, Uni-Lab"
version = "2026.09"
release = "2026.09.07"

extensions = [
    "ai_docs",
    "myst_parser",
]

source_suffix = {
    ".md": "markdown",
}

master_doc = "index"
language = "zh_CN"
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "._*",
    "_static/example-package/README.md",
]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "substitution",
]
myst_heading_anchors = 3

html_theme = "furo"
html_title = "Uni-Lab OS 产品使用说明书"
html_baseurl = ""
html_show_sourcelink = False
html_copy_source = False
html_last_updated_fmt = "%Y-%m-%d"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_js_files = ["ai-docs.js"]

html_theme_options = {
    "navigation_with_keys": True,
    "top_of_page_buttons": [],
    "light_css_variables": {
        "color-brand-primary": "#2757dd",
        "color-brand-content": "#2757dd",
        "color-sidebar-background": "#f8f9fb",
        "color-sidebar-background-border": "#eeebee",
        "color-admonition-background": "#f8f9fb",
        "font-stack": '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
        "font-stack--monospace": 'SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
    },
    "dark_css_variables": {
        "color-brand-primary": "#5ca5ff",
        "color-brand-content": "#5ca5ff",
        "color-background-primary": "#131416",
        "color-background-secondary": "#1a1c1e",
        "color-sidebar-background": "#1a1c1e",
        "color-sidebar-background-border": "#303335",
        "color-admonition-background": "#1a1c1e",
    },
}
