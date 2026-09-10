# 系统安装

:::{admonition} 阅读角色
- **首次使用者**：先安装并验证 Uni-Lab OS，再创建自己的第一个设备包。
- **开发或运维人员**：选择安装方式，维护环境、源码版本和启动配置。
- **验收人员**：确认安装来源、版本、初始 `dry-run` 和停止流程均可追溯。
:::

本页按“**安装 Uni-Lab OS → 下载示例设备包 → 启动示例**”的顺序操作。安装系统时不要求用户提前准备设备包；OS 命令可用后，再下载带有示例驱动、示例工作流和安全启动图的 `demo-lab` 设备包。

:::{important}
第一次启动固定使用示例设备包自带的 `dry-run` 启动图。它只用于验证 OS、设备包发现和工作流加载，不连接真实设备，也不能代替真机安全验收。
:::

## 1. 选择安装路径

系统规划下面两条安装路径；当前请使用可用的源码安装路径：

| 路径 | 适合谁 | 得到什么 |
| --- | --- | --- |
| **一键安装包（暂无法提供）** | 首次体验、演示和不修改 OS 源码的用户 | 已打包的 Uni-Lab OS 运行环境、命令行和操作页面 |
| **Conda/Mamba + `unilabos-env` + 源码** | 需要创建设备包、开发驱动或修改 OS 的用户 | ROS/Python 依赖、可编辑源码，以及仓库内置的轻量操作页面 |

`unilabos-full` 等仿真和可视化环境不是默认安装路径。确实需要 Gazebo、RViz 或 MoveIt 时，再按[环境与运行配置](environment.md)选择。

## 2. 安装前检查

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10/11、Ubuntu 20.04+ 或 macOS 10.15+ |
| Python | 安装路径会准备兼容的 Python 3.11 环境 |
| 磁盘空间 | 至少 10 GB 可用空间 |
| 网络 | 源码安装时能访问 Conda 软件源和 Git 仓库 |
| Conda/Mamba | 两条路径都需要；推荐安装带 `mamba` 的 Miniforge |
| 设备包 | **不需要提前准备**，安装 OS 后再创建 |

如果终端中已经能执行 `conda --version` 或 `mamba --version`，直接选择下一节的一条路径。否则先安装 Miniforge，并重新打开终端。

## 3. 路径一：使用一键安装包

:::{warning}
**一键安装包暂无法提供。** 当前请使用第 4 节“安装 `unilabos-env` 后拉取源码”的方式安装 Uni-Lab OS。
:::

一键安装包适合最快完成首次体验。它已经包含 Uni-Lab OS 运行环境，不需要先克隆仓库或寻找设备包。

### 3.1 获取对应平台的安装包

从交付方取得最新的一键安装包；使用公开构建时，可进入 [GitHub Actions - Conda Pack Build](https://github.com/deepmodeling/Uni-Lab-OS/actions/workflows/conda-pack-build.yml)，选择最新的成功构建并下载对应平台的 Artifact：

- Windows：`unilab-pack-win-64-<branch>.zip`
- macOS Intel：`unilab-pack-osx-64-<branch>.tar.gz`
- macOS Apple Silicon：`unilab-pack-osx-arm64-<branch>.tar.gz`
- Linux：`unilab-pack-linux-64-<branch>.tar.gz`

GitHub Actions 下载的 Artifact 可能还有一层 ZIP 包装；先解开外层 ZIP，再使用里面的平台安装包和安装脚本。

### 3.2 解压并安装

macOS 或 Linux：

```bash
tar -xzf unilab-pack-<platform>-<branch>.tar.gz
cd unilab-pack-<platform>-<branch>
bash install_unilab.sh
conda activate unilab
```

Windows 解压 ZIP 后，双击 `install_unilab.bat`，或在命令行执行：

```batch
install_unilab.bat
conda activate unilab
```

安装脚本会找到本机 Conda、把预打包环境安装为 `unilab`，并完成 `conda-unpack`。已有同名环境时先确认是否允许替换，不要误删仍在使用的环境。

完成后继续执行第 5 节“验证 OS 安装”。

## 4. 路径二：安装 `unilabos-env` 后拉取源码

这条路径适合设备包和驱动开发。`unilabos-env` 只提供 ROS2、Python 依赖和 `uv` 等开发环境；Uni-Lab OS 本身随后从仓库以可编辑模式安装。

### 4.1 安装来源与源码分支

| 内容 | 安装或拉取地址 | 版本或分支 |
| --- | --- | --- |
| **Conda/Mamba** | [Miniforge 官方安装包](https://github.com/conda-forge/miniforge/releases/latest) | 按操作系统和 CPU 架构选择最新的 `Miniforge3` 安装包；不对应 Uni-Lab OS 分支 |
| **`unilabos-env`** | [Anaconda.org：`uni-lab/unilabos-env`](https://anaconda.org/uni-lab/unilabos-env) | 从 `uni-lab` channel 安装；不对应 Git 分支 |
| **Uni-Lab OS 源码** | [GitHub：`Uni-Lab-OS/Uni-Lab-OS`](https://github.com/Uni-Lab-OS/Uni-Lab-OS) | `product/durable-scheduler-kernel-v2` |

Conda/Mamba 是环境管理工具，`unilabos-env` 是 Conda 环境依赖包，Uni-Lab OS 才是需要指定 Git 分支的源码仓库。三者不是同一个安装包，也不共用一个“分支”概念。

### 4.2 创建并激活环境

下面的 `unilabos-env` 安装方式与仓库根目录的 `README_zh.md` 保持一致：

```bash
mamba create -n unilab python=3.11.14
mamba activate unilab
mamba install uni-lab::unilabos-env -c robostack-staging -c conda-forge
```

如果使用 Conda 激活环境，也可以执行 `conda activate unilab`。后续所有命令必须在同一个 `unilab` 环境中运行。

### 4.3 克隆 `kernel-v2` 分支并安装 Uni-Lab OS

```bash
git clone \
  --branch product/durable-scheduler-kernel-v2 \
  --single-branch \
  https://github.com/Uni-Lab-OS/Uni-Lab-OS.git
cd Uni-Lab-OS
pip install -e .
uv pip install -r unilabos/utils/requirements.txt
```

已经克隆过该仓库时，在仓库目录内更新同一分支：

```bash
git switch product/durable-scheduler-kernel-v2
git pull --ff-only origin product/durable-scheduler-kernel-v2
```

源码仓库已经包含构建好的轻量操作页面，位于 `unilabos/app/web/static/console/`，会随 Uni-Lab OS 一起提供。只使用页面时不需要执行 `npm install` 或单独启动前端；只有修改 `frontend/` 源码时，才需要 Node.js 并重新执行前端测试和构建。

:::{note}
`pip install -e .` 让本地源码修改立即生效；`uv pip install` 安装运行所需的 pip 依赖。以后切换仓库分支或拉取新代码时，应重新验证依赖和命令版本。
:::

## 5. 验证 OS 安装

无论选择哪条路径，都先确认当前终端使用的是刚安装的环境：

```bash
conda activate unilab
python -c "import unilabos; print(unilabos.__version__)"
unilab --help
unilab workspace --help
```

四条命令都成功，才说明 OS 已经安装。此时即使本机还没有任何用户设备包，安装也已经完成。

## 6. 下载并安装示例设备包

当前分支尚未提供 `unilab workspace init`，不能通过命令自动生成设备包。首次体验请先下载已经准备好的示例设备包：

:::{admonition} 示例文件下载
:class: note

- {download}`下载 demo-lab.zip <_static/example-package/demo-lab.zip>`
- [查看示例设备包说明](demo-lab.md)
:::

将下载的压缩包放到准备使用的目录，解压后进入设备包：

```bash
unzip demo-lab.zip
export DEVICE_PACKAGE_ROOT="$(pwd)/demo-lab"
cd "$DEVICE_PACKAGE_ROOT"
```

安装示例设备包并执行本地检查：

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
unilab package inspect --path . --out dist/inspect
```

这些检查通过后，只能说明教学设备包可以被发现和静态解析，不表示任何真实设备已经接入。

## 7. 以安全模式启动

第一次启动显式指定示例设备包自带的启动图，避免读取其他项目或旧环境的默认配置：

```bash
unilab workspace start \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --component all \
  --graph "$DEVICE_PACKAGE_ROOT/deployment/graphs/dry-run.json" \
  --runtime-mode dry-run \
  --startup-mode develop \
  --json
```

查看状态：

```bash
unilab workspace status \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --json
```

操作页面地址以状态命令实际输出为准。源码路径安装时，页面由 Workspace Backend 直接从 `/console/` 提供，不需要再运行一个独立前端服务。

如果启动失败，先查看组件日志，不要改用真实设备配置反复尝试：

```bash
unilab workspace logs \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --component backend \
  --json
```

结束体验后停止工作区：

```bash
unilab workspace stop \
  --workspace "$DEVICE_PACKAGE_ROOT" \
  --component all \
  --json
```

## 8. 从示例转为真实设备包

确认 OS、设备包示例和 `dry-run` 都能正常工作后，再按以下顺序替换示例内容：

1. 填写 `DEVICE_PACKAGE_REQUIREMENTS.md`，记录设备型号、协议、动作、单位和安全边界；
2. 按[设备接入模板](device-template.md)实现真实驱动；
3. 按[物料定义模板](material-template.md)登记物料与位置；
4. 新建独立的联调或生产启动图，不修改教学 `dry-run.json` 来承载生产地址；
5. 按[工作流运行](workflow.md)编写和验证工作流；
6. 完成[设备包验收](scenario-guide.md)后，才进入受控真机运行。

安装和初次启动的最短顺序始终是：**先安装 OS，再创建设备包，最后启动设备包**。用户不需要为了安装 Uni-Lab OS 预先取得一个现场设备包。
