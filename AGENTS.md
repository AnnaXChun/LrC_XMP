# Agent 使用与协作约定

本文件是使用 LrC_XMP 的执行入口，适用于能操作本地终端与文件的 Agent。默认使用简体中文。

用户说“帮我使用这个仓库”“给照片套用预设”时，直接完成环境准备、试色、核对和文件交付。除非缺少必要权限或输入，不要停留在操作教程。用户给定的照片、输出位置和预设范围优先于下方默认值。

## 前置要求

| 项目 | 要求与处理方式 |
| --- | --- |
| Agent 能力 | 能读取文件、运行命令、安装项目依赖并返回文件链接。纯聊天环境无法执行时，明确说明缺少什么能力 |
| 仓库访问 | 本仓库目前为私有，需要已有读取权限；也可使用用户提供的 ZIP 解压副本。复用已有 GitHub 登录，不要求用户在聊天中粘贴 Token |
| 获取方式 | 有 Git 时克隆仓库；已有副本时先核对远端和工作树，不覆盖用户改动。不强制安装 Git，ZIP 副本也能运行 |
| Python 与 uv | 项目要求 Python 3.12 或更高版本；默认选 3.12，使用 uv 和锁文件准备环境。缺少 uv 时按[官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)选择当前系统的用户级安装方式 |
| 网络 | 首次获取仓库、Python、依赖及演示原图时需要网络。环境和输入齐全后，照片处理在本地完成 |
| 系统 | 当前执行记录来自 macOS、Python 3.12.14。Windows／Linux 需在目标机器检查，不能沿用 macOS 的验证结论 |
| 输入照片 | 支持不透明 RGB／灰度 JPG、PNG、TIFF、WebP。页面及批量接口每张最多 25 MB，输出长边最多 1200 像素 |
| 中文字体 | 生成样张总览图需要 CJK 字体；支持自动查找 macOS 黑体、Linux Noto Sans CJK、Windows 微软雅黑，也可用 `--font` 指定。自己的照片批量预览不需要字体 |
| Adobe | Python 试色无需 Adobe 账号、Lightroom、API Key 或 GPU。Lightroom 验证是独立的可选流程 |

不需要创建 `.env`。依赖以 [pyproject.toml](pyproject.toml) 和 [uv.lock](uv.lock) 为准；不要为了普通使用升级依赖或重写锁文件。

## 先确定本次输入

1. 定位仓库根目录，读取 [README](README.md) 和 [预设制作约定](docs/预设制作约定.md)，核对 [Python 预览说明](docs/Python预览.md) 中的处理范围。
2. 用户已提供本地照片或 Agent 可读的附件时，使用这些文件；只处理用户指定的文件或目录。
3. 用户只是想先试用时，默认跑仓库的全部样张、全部预设，无需再问风格偏好。
4. 用户明确要求“用我的照片”，但文件不可读时，请其提供可访问的位置；等待期间可以完成环境准备。样张结果必须标成演示，不能替代用户照片交差。
5. HEIC、RAW／DNG 或透明图片不能直接送入当前预览器。说明格式要求，保留原文件；需要转换时使用新的副本，并记录转换方式。不要把 RAW 内嵌预览称为 RAW 解码结果。

全部预设以 `lrc_xmp.catalog.discover_presets()` 的返回值为准，不要把 README 的数量硬编码进脚本。用户只指定部分预设时，使用返回的名称或文件路径做精确筛选，并报告实际选择。

## 准备环境与配置

在仓库根目录运行：

```bash
uv --version
uv sync --locked --python 3.12
uv run --locked python --version
```

没有 uv 时，先完成上表中的安装步骤，再运行这些命令。安装限于项目及当前用户环境，不自动安装 Adobe、不申请管理员权限、不修改系统级 Python。

批量处理无需启动服务。用户希望保留可点击的试色页面时，使用：

```bash
uv run --locked --extra ui streamlit run app.py --server.headless true
```

[页面配置](.streamlit/config.toml) 已提供下列默认值：

| 配置 | 默认值 |
| --- | --- |
| 服务地址 | `127.0.0.1`，仅本机访问 |
| 端口 | Streamlit 默认 `8501` |
| 单图上传上限 | `25 MB` |
| 使用统计 | 关闭 |
| 输出尺寸 | 批量接口与页面长边最多 `1200` 像素 |
| 输出目录 | 批量结果使用 `local/` 中新建的目录；页面结果通过下载保存 |

端口被占用时，选择空闲端口，通过 `--server.port` 显式传入，并交付实际地址。不要结束占用端口的其他进程，也不要改绑公网地址。只有服务存活且 `/_stcore/health` 返回成功，才报告“页面已启动”。

远程容器中的 `127.0.0.1` 不等于用户电脑的本地地址。没有可用端口转发时，交付下载文件；不要把用户无法访问的地址当成可用入口。需要让页面继续运行时，使用环境支持的持久进程，记录停止方式。

## 生成样张对照

没有指定照片时运行：

```bash
uv run --locked python -m lrc_xmp.demo
```

程序会校验或下载 [样张清单](examples/sources.json) 中的照片，应用全部预设，并创建新的 `local/preview-日期时间/`。以命令实际输出的 `Gallery:` 路径为准。

可选参数为 `--output`、`--font`、`--presets`。输出目录必须尚不存在。`--inputs` 是登记样张的下载缓存目录，不是任意照片文件夹入口。

缺少中文字体时，先查找已有字体并用 `--font` 指定。当前程序在写总览图前可能已生成部分结果；补齐字体后用新目录重跑，不将残留目录当成完整交付。离线且原始样张未缓存时，可以查看仓库自带的对照图，但必须注明使用既有产物，不能声称本次重新渲染。

## 处理用户照片

使用已有的 `preview_all` 接口。它与页面共用处理逻辑，接收照片副本，返回原图预览、全部调色图、逐图报告、错误清单及 ZIP 字节。

下面是可直接执行的最小脚本。在仓库根目录启动 Python，通过标准输入执行；也可将脚本保存在仓库根目录，使用未占用的临时文件名，便于导入本项目模块。将用户照片路径作为命令行参数传入，并按当前 Shell 正确引用。Windows PowerShell 推荐临时脚本方式；完成后删除自己新建的临时脚本。

```python
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from lrc_xmp.batch import preview_all
from lrc_xmp.catalog import ROOT, discover_presets

if not sys.argv[1:]:
    raise SystemExit("请把照片路径作为参数传入。")

variants = discover_presets()
(ROOT / "local").mkdir(exist_ok=True)
output = Path(tempfile.mkdtemp(prefix="agent-", dir=ROOT / "local"))
manifest = {"renderer": "Python approximate", "adobe_equivalent": False,
            "lightroom_verified": False, "preset_count": len(variants),
            "inputs": []}

for index, argument in enumerate(sys.argv[1:], 1):
    source = Path(argument).expanduser().resolve()
    item = {"input": source.name}
    try:
        data = source.read_bytes()
        source_hash = hashlib.sha256(data).hexdigest()
        result = preview_all(data, source.suffix, variants)
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError("源照片在运行期间发生变化，请检查。")
        bundle = output / f"photo-{index:03d}.zip"
        bundle.write_bytes(result["zip"])
        item.update(input_sha256=source_hash, bundle=bundle.name,
                    expected=len(variants), completed=len(result["results"]),
                    errors=result["errors"])
    except (ValueError, OSError) as error:
        item.update(completed=0, errors=[str(error)])
    manifest["inputs"].append(item)

manifest["status"] = "complete" if all(
    item.get("completed") == len(variants) and not item["errors"]
    for item in manifest["inputs"]) else "partial"
(output / "delivery.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(output)
print(manifest["status"])
```

通过标准输入执行时，命令为 `uv run --locked python - 照片路径`；使用临时脚本时，命令为 `uv run --locked python 临时脚本路径 照片路径`。两种方式都支持追加多个照片路径。脚本输出目录和 `complete／partial` 状态；Agent 必须继续核对和整理交付。脚本中的 RuntimeError 表示源照片发生变化，应停止并说明，不能继续宣称原图完整。

每个 ZIP 自带 `before.png`、`result-N.png`、同名 JSON、名称映射 `index.json` 和 `说明.txt`。解压到新的独立子目录后，直接使用这些图片做并排展示；文件名中的 N 与 `index.json` 对应，不要猜预设名称。该接口允许带报告的部分近似，跳过项见每张结果的 `coverage`。

用户指定部分预设时，执行前调整 `variants` 的筛选，并确认不为空。不要改动 XMP 数值或另写一套调色算法。

## 验收后再交付

- 核对实际照片数、预设数和成功组合数。每个预期组合应有 PNG 及对应报告；有失败项时报告部分完成和具体原因。
- 核对报告中的 `input_sha256`、`preset_sha256`、`output_sha256`，以及 `source_files_unchanged`。批量接口的输入文件名是临时副本名，原文件与 ZIP 的对应关系查 `delivery.json`。
- 再次检查原照片与 XMP 的哈希；交付的 XMP 副本必须与源文件一致。不要用 PNG 文件哈希跨次运行判断视觉是否相同，ICC 创建时间可能改变文件字节。
- 至少查看一张完整对照，确认原图与结果配对、方向、裁切和中文标注。无法查看时标为“未进行视觉检查”。
- 查看每份报告的 `coverage`。主版当前跳过 Adobe Color、RAW 白平衡和相机校准等 8 项设置；其他标量和曲线仍采用独立近似模型。不能写成完整还原 Lightroom。
- 页面健康检查、框架测试、真实浏览器操作和 Lightroom 实测分别记录。只启动服务不能证明上传、按钮和下载已通过浏览器验证。

普通使用按实际产物核对即可。修改代码时，按影响范围运行测试；完整命令为 `uv run --locked --extra ui pytest -q`。不要仅引用仓库旧测试记录，声称本次已经测试。

## 最终交付的产物

将本次结果整理到一个新目录。以下前两种模式各有现成产物，其余由 Agent 在验收后补齐；它们不会因为运行了一条命令就全部自动生成。

| 产物 | 具体要求 |
| --- | --- |
| 可直接查看的对照 | 样张模式交付 `index.html`、`contact-sheet.png` 及完整图片目录；用户照片模式解压批量 ZIP，提供原图与结果的并排展示或本地 `index.html`，同时保留所有版本 |
| 调色图片 | 每张输入对应全部选定预设的 PNG，长边最多 1200 像素；原图预览标明为 sRGB 归一化副本 |
| 参数与执行报告 | 保留每张结果 JSON、名称映射及运行汇总。汇总写清版本或提交、输入数、预设数、成功／失败数、跳过项、原文件保护检查、视觉／浏览器／Lightroom 验证状态 |
| 可复用预设 | 原样复制本次使用的 XMP，以及同名 `.source.json`、`.verification.json`，保留目录关系；缺少配套记录时如实列明 |
| 下载包 | 提供一个包含以上产物的 ZIP；只能打包本次交付目录，不能打包整个仓库、`.venv`、原始照片或缓存 |
| 可选试色页面 | 用户需要继续选图时，提供已确认可访问的本地地址、启动命令和停止方式。页面只是额外入口，处理结果仍需保存成文件 |

最终回复先给可点击的对照、下载包和预设路径，再说明处理了哪些照片、成功多少组合、有哪些未验证项。给出一条能重复执行本次任务的命令；有网页时说明其运行位置。不要只交源代码或启动截图。

用户没有要求上传、分享或发布本次照片时，产物留在本地。演示样张的发布遵循来源许可，用户照片与渲染结果不会因为使用本仓库而自动获得上传授权。

## 可选的 Lightroom 安装与验证

仅在用户要求且已有可用授权环境时执行。先检查 Lightroom 实际使用的预设目录和是否随目录保存预设；安装采用新文件，不覆盖同名文件。需要重启时先征得同意。

在测试副本或虚拟副本上导入，确认预设面板显示，再应用并读回参数。存在 Lightroom MCP 时使用它核对。有任何环节不可用，分别标为未验证；不能只保存到 MCP 插件内部的隐藏预设，也不能以 Python 结果代替 Lightroom 验证。

## 维护预设与代码时的规则

- 用户给定数值必须原样保留；未指定设置不补默认值。
- `confirmed` 表示参数有来源，不表示已通过 Lightroom 实测。
- 作品仿色归入风格研究，不能署为摄影师本人发布的参数。
- 每份预设保留来源与验证记录；修改时检查字段遗漏和多写。
- 新变体使用不同名称和 UUID，不覆盖已有同名预设。
- 不修改原始照片。文件检查、软件导入、面板显示、照片应用和参数读回分别报告。
- 不上传凭证、个人照片、第三方原视频、本地诊断路径或个人工具配置。普通试用不需要提交或推送仓库。
- 新增预设后，重跑全部对照，更新 README 的数量、样片和适用说明。具体规则见 [预设制作约定](docs/预设制作约定.md)。
