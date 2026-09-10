# demo-lab 演示说明

:::{admonition} 示例文件下载
:class: note

- {download}`下载 README.md <_static/example-package/README.md>`
- {download}`下载 demo-lab.zip <_static/example-package/demo-lab.zip>`
:::

这个文件夹是一套**演示示例**。业务是「标准样品称量分装」：取母液 → 称量 → 分装到空瓶 → 封盖 → 成品回 `F01`，母液回 `U01`。

全程是电脑里的模拟设备，**不接真实仪器，也不需要 PLC**。下面每一步都是真实的 `unilab` 命令和接口。

操作顺序固定为：

1. 启动工作区  
2. 查询有哪些工作流  
3. 选一个工作流，指定实验参数、物料、库位  
4. 系统做执行前预检查，并给出检查结果  
5. 物料不足或库位被占用时，按给出的办法自行处理后，再预检  
6. 预检查通过后启动工作流，并查看执行结果  

## 开始前确认这两件事

1. 这台电脑已经装好 **Uni-Lab OS**。还没有的话，先按[系统安装](installation.md)完成 Conda 环境、`unilabos-env` 和 Uni-Lab OS 源码安装。

装好后先确认命令可用：输入 `unilab` 再按回车，应看到命令说明。找不到命令时执行 `conda activate unilab`（或 `mamba activate unilab`），再试一次。

2. 进入本演示目录：

```bash
cd /path/to/demo-lab
```

## 1. 安装并启动工作区

```bash
python -m pip install -e .
unilab package inspect --path . --out ./dist/inspect

unilab workspace start \
  --workspace . \
  --graph deployment/graphs/dry-run.json \
  --runtime-mode normal \
  --startup-mode develop \
  --wait 300
```

`--runtime-mode normal` 会调用本包的 Python 模拟设备。称量结果应是 `12.5` 克，分装体积等于任务里填的微升数。改成 `dry-run` 时任务也能成功，但这两个数会是 `0`。

```bash
unilab workspace status --workspace . --json
```

记下 Backend 的 `address`，端口每次启动可能不同。

```bash
export API="$(unilab workspace status --workspace . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["components"]["backend"]["address"])')/api/v1"
echo "$API"
```

## 2. 查询有哪些工作流

```bash
python - <<'PY'
import json, os, urllib.request
with urllib.request.urlopen(f"{os.environ['API']}/workflows?page=1&page_size=100") as r:
    items = json.load(r)["data"]["items"]
print("工作流数量", len(items))
for item in items:
    print({
        "uuid": item.get("uuid"),
        "名称": item.get("name"),
        "状态": item.get("status"),
        "类型": item.get("workflow_type"),
        "修订": item.get("revision"),
    })
PY
```

这套演示里通常只有一条：**标准样品称量分装**  
`7e2a9c14-6b5d-4f81-a3c0-91d8e4b2f6a5`。

`status=source` 表示还不能建实验任务，先发布：

```bash
export WF="7e2a9c14-6b5d-4f81-a3c0-91d8e4b2f6a5"
python - <<'PY'
import json, os, urllib.request
api, wf = os.environ["API"], os.environ["WF"]

def get(path):
    with urllib.request.urlopen(f"{api}{path}") as r:
        return json.load(r)["data"]

workflow = get(f"/workflows/{wf}")
authoring = get(f"/workflows/{wf}/authoring")
print("当前", workflow["status"], "修订", workflow["revision"], "创作", authoring["state"], authoring["workflow_revision"])
if workflow.get("status") != "published":
    req = urllib.request.Request(
        f"{api}/workflows/{wf}/publications",
        data=json.dumps({"revision": int(authoring["workflow_revision"])}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        print("发布", json.load(r).get("code"))
    print("发布后", get(f"/workflows/{wf}")["status"])
PY
```

发布后列表里应变为 `published`，才能进入下一步。

## 3. 选择工作流，指定实验参数、物料、库位

选定上面的 `WF` 后，先看这条工作流要哪些输入，再看现场物料和库位。

```bash
python - <<'PY'
import json, os, urllib.request
with urllib.request.urlopen(f"{os.environ['API']}/workflows/{os.environ['WF']}") as r:
    data = json.load(r)["data"]
print("已选", data.get("name"), data.get("uuid"), data.get("status"))
print("说明", data.get("description"))
PY
```

### 3.1 实验参数、物料、库位怎么填

建任务时全部放在 `input` 里。

| 字段 | 类别 | 含义 | 本演示可填值 |
| --- | --- | --- | --- |
| `sample_id` | 实验参数 | 样品编号，出现在封盖结果里 | 任意字符串，默认 `ASSAY-2026-001` |
| `target_aliquot_volume_ul` | 实验参数 | 分装体积 | 整数 1–5000，默认 `200` |
| `source_stock_site` | 库位 | 母液从哪取 | 目前只能 `S01` |
| `source_empty_site` | 库位 | 空瓶从哪取 | 目前只能 `E01` |
| `tip_box_site` | 库位 | 吸头从哪取 | 目前只能 `T01` |
| `used_stock_target_site` | 库位 | 用过的母液放哪 | 目前只能 `U01` |
| `product_vial_target_site` | 库位 | 成品放哪 | 目前只能 `F01` |

物料不是在任务里填瓶子 UUID。工作流按**库位 + 类型**取当时占着那个格子的瓶子：

- `S01` 上必须是母液瓶（`stock_vial`）  
- `E01` 上必须是空分装瓶（`aliquot_vial`）  
- `T01` 上必须是吸头盒（`tip_box`）  
- `U01` / `F01` / `BAL1` / `PIP_S` / `PIP_T` / `CAP1` / `GRIPPER` 启动时应为空  

换一瓶同类型的瓶子：把新瓶放到对应格子即可，不用改工作流。换库位名（例如改成 `S02`）要改源码和图，见第 6 节。

### 3.2 先看现场有没有料、格子空不空

```bash
python - <<'PY'
import json, os, urllib.request
with urllib.request.urlopen(f"{os.environ['API']}/materials/graph") as r:
    nodes = json.load(r)["data"]["nodes"]
names = {n["material"]["uuid"]: n["material"]["name"] for n in nodes}
print("库位占用：")
for n in nodes:
    for site in n.get("sites") or []:
        occ = site.get("occupied_material_uuid")
        print(f"  {site.get('name')}: {names[occ] if occ else '空'}")
PY
```

启动后第一次应看到：`S01` 母液、`E01` 空瓶、`T01` 吸头盒，其余为空。前端物料/布局页看的是同一份数据。

把这次实验要跑的参数写成文件：

```bash
export SAMPLE_ID="ASSAY-2026-001"
export VOLUME_UL=200

python - <<'PY'
import json, os
from pathlib import Path
Path("/tmp/demo-lab-input.json").write_text(json.dumps({
    "sample_id": os.environ["SAMPLE_ID"],
    "target_aliquot_volume_ul": int(os.environ["VOLUME_UL"]),
    "source_stock_site": "S01",
    "source_empty_site": "E01",
    "tip_box_site": "T01",
    "used_stock_target_site": "U01",
    "product_vial_target_site": "F01",
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(Path("/tmp/demo-lab-input.json").read_text())
PY
```

称量结果在这套演示里固定是 `12.5` 克，改体积不会改变它。

## 4. 执行前预检查

```bash
python - <<'PY'
import json, os, urllib.request
from pathlib import Path

payload = {"run_mode": "normal", "input": json.loads(Path("/tmp/demo-lab-input.json").read_text())}
req = urllib.request.Request(
    f"{os.environ['API']}/workflows/{os.environ['WF']}/run-preflight",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    data = json.load(r)["data"]

print("预检状态", data.get("status"))
print("能否现在跑", data.get("can_run"))
print("摘要", data.get("summary"))
print("检查项：")
for item in data.get("checks") or []:
    print({
        "类型": item.get("type"),
        "结果": item.get("status"),
        "代码": item.get("code"),
        "说明": item.get("message"),
        "是否阻断": item.get("blocking"),
        "节点": item.get("node_name"),
    })
PY
```

| 预检 `status` | 含义 |
| --- | --- |
| `runnable_now` | 当前检查通过，可以建任务 |
| `temporarily_unavailable` | 有阻断项，先处理再预检 |
| 检查项 `passed` | 这项没问题 |
| 检查项 `deferred` | 这项会在建任务/派发时再核一次 |
| 检查项 `blocked` | 这项不过，不能建任务 |

物料来源在这套系统里常常标成 `deferred`（准入时再解析），所以**预检通过不等于原料区一定有瓶子**。预检之后再看一遍第 3.2 节的库位占用。出现下面情况时，不要建任务，先做第 5 节：

- `S01` / `E01` / `T01` 为空（物料不足，或上一遍已经搬走）  
- `U01` / `F01` 或工艺位上有东西（回库位/工艺位被占用）  
- 预检 `can_run=false`，或检查项 `blocked`  

## 5. 预检未通过时自行处理

按检查结果和库位占用选一种办法，做完再回到第 4 节预检。

| 现象 | 原因 | 自己可以做的处理 |
| --- | --- | --- |
| `S01` / `E01` / `T01` 为空 | 上一遍已跑完，瓶子到了 `U01` / `F01` | 整盘恢复，或人工把原瓶放回去 |
| `F01` / `U01` / `BAL1` 等被占用 | 回库位或工艺位上有上一遍留下的瓶子 | 先把占用取下，或整盘恢复 |
| 想换一瓶同类型的料 | 格子上不是你要的那瓶 | 下料后把新瓶放到同一格子 |
| 想改用别的库位名 | 源码只允许 `S01` 等字面量 | 改载架、启动图、工作流后重启并重新发布 |

### 办法 A：按启动图整盘恢复（最常用）

```bash
unilab workspace reset-local \
  --workspace . \
  --graph deployment/graphs/dry-run.json \
  --runtime-mode normal \
  --yes

unilab workspace start \
  --workspace . \
  --graph deployment/graphs/dry-run.json \
  --runtime-mode normal \
  --startup-mode develop \
  --wait 300
```

复位后 Backend 地址可能变，重新设置 `$API`。`reset-local` 会把工作流打回 `source`，必须先按第 2 节重新发布，再从第 3.2 节看库位并预检。有未结束的任务时复位会失败，先取消任务。

### 办法 B：人工把已有瓶子放到指定空位

目标格必须是空的。例如把母液放回 `S01`、空瓶放回 `E01`、吸头放回 `T01`：

```bash
python - <<'PY'
import json, os, urllib.request

api = os.environ["API"]

def get(path):
    with urllib.request.urlopen(f"{api}{path}") as r:
        return json.load(r)["data"]

def put(path, body):
    req = urllib.request.Request(
        f"{api}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)

nodes = get("/materials/graph")["nodes"]
site_by_name, material_by_name = {}, {}
for n in nodes:
    material_by_name[n["material"]["name"]] = n["material"]["uuid"]
    for site in n.get("sites") or []:
        site_by_name[site.get("name")] = {
            "uuid": site["uuid"],
            "occupied": site.get("occupied_material_uuid"),
        }

for material_name, site_name in (
    ("标准样品母液 001", "S01"),
    ("空分装瓶 001", "E01"),
    ("吸头盒 001", "T01"),
):
    site = site_by_name[site_name]
    material_uuid = material_by_name[material_name]
    if site["occupied"] == material_uuid:
        print(material_name, "已经在", site_name)
        continue
    if site["occupied"]:
        raise SystemExit(f"{site_name} 已被占用，先下料或改用 reset-local")
    result = put(f"/materials/{material_uuid}", {
        "site_placement": {"action": "place", "site_uuid": site["uuid"]},
    })
    print("上料", material_name, "->", site_name, "code", result.get("code"))
PY
```

只下料、不删瓶子：

```bash
python - <<'PY'
import json, os, urllib.request
api = os.environ["API"]
with urllib.request.urlopen(f"{api}/materials/graph") as r:
    nodes = json.load(r)["data"]["nodes"]
stock = next(n["material"]["uuid"] for n in nodes if n["material"]["name"] == "标准样品母液 001")
req = urllib.request.Request(
    f"{api}/materials/{stock}",
    data=json.dumps({"site_placement": {"action": "remove"}}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
with urllib.request.urlopen(req) as r:
    print("下料", json.load(r).get("code"))
PY
```

### 办法 C：换一瓶同类型物料（库位名不变）

工作流认格子上的类型，不认某一个 UUID。把旧瓶 `remove`，`POST /materials` 建新瓶，再 `place` 到空的 `S01` / `E01` / `T01`。

```bash
python - <<'PY'
import json, os, urllib.request

api = os.environ["API"]

def get(path):
    with urllib.request.urlopen(f"{api}{path}") as r:
        return json.load(r)["data"]

def call(method, path, body=None):
    req = urllib.request.Request(
        f"{api}{path}",
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)

templates = get("/resource-templates?page=1&page_size=100")
items = templates.get("items") if isinstance(templates, dict) else templates
stock_tpl = next(
    t for t in items
    if t.get("name") in {"stock_vial", "标准样品母液瓶"}
    or "stock_vial" in str(t.get("class") or t.get("name") or "")
)
nodes = get("/materials/graph")["nodes"]
s01 = next(site for n in nodes for site in (n.get("sites") or []) if site.get("name") == "S01")
if s01.get("occupied_material_uuid"):
    call("PUT", f"/materials/{s01['occupied_material_uuid']}", {"site_placement": {"action": "remove"}})
created = call("POST", "/materials", {
    "resource_template_uuid": stock_tpl["uuid"],
    "name": "标准样品母液 002",
    "barcode": "ASSAY-STOCK-002",
})["data"]
placed = call("PUT", f"/materials/{created['uuid']}", {
    "site_placement": {"action": "place", "site_uuid": s01["uuid"]},
})
print("已换料到 S01", created["name"], "code", placed.get("code"))
PY
```

`E01` 对应 `aliquot_vial`，`T01` 对应 `tip_box`。

### 办法 D：更换工作流使用的库位名

任务 `input` 里把 `source_stock_site` 改成 `S02` 现在会失败，因为源码是 `Literal["S01"]`。要同时改：

1. `demo_lab/resources/carriers.py` 的 `available_sites`（必须是字面量数组）和 `_rack` 格子  
2. `scripts/write_simulation_graph.py`，然后 `python scripts/write_simulation_graph.py`  
3. `demo_lab/workflows/weigh_aliquot.py` 的 `Literal` 和默认值  
4. `unilab workspace stop` → `reset-local` → `start` → 重新发布  

工艺位 `BAL1` / `PIP_S` / `PIP_T` / `CAP1` 写在搬运步骤里，不是任务参数。

## 6. 预检查通过后启动工作流

确认预检是 `runnable_now`，并且 `S01` / `E01` / `T01` 有料、回库位为空，再创建任务：

```bash
python - <<'PY'
import json, os, time, urllib.request
from pathlib import Path

api, wf = os.environ["API"], os.environ["WF"]
payload = {
    "workflow_uuid": wf,
    "run_mode": "normal",
    "priority": "normal",
    "input": json.loads(Path("/tmp/demo-lab-input.json").read_text()),
    "inventory_bindings": [],
    "description": f"标准样品称量分装-{os.environ['SAMPLE_ID']}",
}
req = urllib.request.Request(
    f"{api}/workflow-tasks",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    task = json.load(r)["data"]
print("任务", task["uuid"], "初始状态", task["status"])

done = {"succeeded", "failed", "cancelled", "canceled", "aborted"}
for _ in range(90):
    with urllib.request.urlopen(f"{api}/workflow-tasks/{task['uuid']}") as r:
        current = json.load(r)["data"]
    print("进度", current["status"])
    if current["status"] in done:
        output = current.get("output") or {}
        print("执行结果")
        print("  称量", output.get("measured_mass_g"), "克")
        print("  分装体积", output.get("commanded_volume_ul"), "微升")
        print("  封盖说明", output.get("message"))
        print("  成品", output.get("product_vial"))
        print("  已用母液", output.get("used_stock_vial"))
        print("  错误", current.get("error_info"))
        break
    time.sleep(1)
PY
```

成功时 `status=succeeded`。`normal` 下称量应是 `12.5`，分装体积等于你填的数。

看每一步：

```bash
python - <<'PY'
import json, os, urllib.request
with urllib.request.urlopen(f"{os.environ['API']}/workflow-tasks") as r:
    items = json.load(r)["data"]["items"]
task = items[0]["uuid"]
with urllib.request.urlopen(f"{os.environ['API']}/workflow-tasks/{task}/jobs") as r:
    raw = json.load(r)["data"]
jobs = raw if isinstance(raw, list) else (raw or {}).get("items") or []
print("作业数", len(jobs))
for job in jobs:
    print(job.get("executor_kind"), job.get("status"))
PY
```

再看一遍库位：成品应在 `F01`，母液应在 `U01`。这时不要直接再创建任务，先按第 5 节恢复原料区，再从第 3.2 节重新指定参数并预检。

停止工作区：

```bash
unilab workspace stop --workspace .
```

## 打开前端

页面跟着工作区走，不用另装前端。本包默认不自动弹浏览器。

```bash
unilab workspace status --workspace . --json \
  | python -c 'import json,sys,webbrowser; url=json.load(sys.stdin)["components"]["backend"]["address"]+"/console/"; print(url); webbrowser.open(url)'
```

页面上的按钮名和接口文档不完全一样，按这个点：

1. 左侧 **工作流** → 目录里选「标准样品称量分装」。状态是 `source` 时点 **发布**。  
2. 点 **进入运行准备**。来源库位是下拉框，**只列出当前有对应物料的格子**（例如 `原料载架 / S01 · 标准样品母液 001`）。`S01` / `E01` 为空时会出现「没有符合要求的有料库位」，这时不要提交，先按第 5 节恢复。  
3. 点 **运行 Preflight**。通过后底部会显示「当前可提交，派发时仍会复核」。  
4. 点 **提交任务**。页面会跳到 **任务**，等 14 个节点变绿。点最后的 **结果汇总**，`measured_mass_g` 应是 `12.5`，`commanded_volume_ul` 等于你填的体积。  
5. 看占用：打开 **物料**，先点开 **主工作台**，再看原料载架 / 成品区 / 已用母液区 / 吸头仓。

侧栏可能仍写着「深圳实验室 / SZLab Edge」，总监控里的工站图也不是这套演示的 `S01`/`E01`。以工作流、物料、任务三页为准。

## 这套演示里有什么

| 名称 | 可以把它理解成 |
| --- | --- |
| 搬运机器人 | 在各个工位之间搬瓶子 |
| 天平工站 | 称母液瓶 |
| 移液工站 | 按体积分装 |
| 封盖工站 | 给分装瓶盖盖 |
| 母液瓶 / `S01` | 标准样品来源 |
| 空分装瓶 / `E01` | 用来接收分装液体 |
| 吸头盒 / `T01` | 移液用的耗材 |
| 成品区 / `F01` | 封盖后的瓶子放这里 |
| 已用区 / `U01` | 用过的母液放这里 |

启动图 `deployment/graphs/dry-run.json` 里的 `occupied_by` 决定第一次启动时瓶子在哪。

## 常见情况

| 你看到的 | 怎么处理 |
| --- | --- |
| 找不到 `unilab` | 先 `conda activate unilab`，再输入 `unilab` |
| 工作流是 `source` | 按第 2 节发布后再选它建任务；`reset-local` 之后也会变回 `source` |
| 预检 `can_run=false` 或原料区为空 | 按第 5 节恢复或上料，再预检 |
| 想换瓶子或换格子 | 换瓶用第 5 节办法 C；换库位名用办法 D |
| 分装体积报错 | `target_aliquot_volume_ul` 只能是 1 到 5000 的整数 |
| 启动很久没有就绪 | `unilab workspace stop --workspace .` 后再 `workspace start` |
| 页面连不上 | 工作区没启动，或复位后端口变了，重新看 `workspace status` |

`.unilabos` 是本机运行记录，拷贝仓库时不用带上。
