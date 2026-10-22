"""Download checksum-pinned samples and build an offline comparison gallery."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import html
import json
from pathlib import Path
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .preview import load_srgb, preview, save_png, sha256

ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    "grade": ROOT / "presets/partial/平川参考_仅已知颜色分级.xmp",
    "main": ROOT / "presets/confirmed/品川力仿色_原视频确认值_ProRAW.xmp",
}
LABELS = {"before": "原图 · sRGB", "grade": "仅颜色分级 · 近似", "main": "主版 · 部分近似"}


def fetch(sample: dict, input_dir: Path) -> Path:
    path = input_dir / sample["filename"]
    if path.exists():
        if sha256(path) != sample["sha256"]:
            raise ValueError(f"已下载文件与登记哈希不符：{path.name}")
        return path
    request = urllib.request.Request(sample["download_url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    import hashlib
    if len(data) > 20 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != sample["sha256"]:
        raise ValueError(f"下载内容改变或体积超限：{sample['id']}，请重新核对来源。")
    with path.open("xb") as stream:
        stream.write(data)
    return path


def font(size: int, custom: Path | None = None):
    candidates = [custom] if custom else [
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    ]
    for path in candidates:
        if path and path.exists():
            return ImageFont.truetype(str(path), size)
    raise ValueError("生成中文总览图需要 CJK 字体，请用 --font 指定字体文件。")


def make_sheet(samples: list[dict], output: Path, custom_font: Path | None) -> None:
    width, gutter, cell_w, photo_h, row_h = 1488, 24, 472, 520, 594
    sheet = Image.new("RGB", (width, 184 + len(samples) * row_h + 84), "#f5f3ed")
    draw = ImageDraw.Draw(sheet)
    draw.text((gutter, 22), "预设试片", font=font(38, custom_font), fill="#202321")
    draw.text((gutter, 78), "Python 近似结果；主版未应用 Adobe Color、RAW 白平衡及相机校准。",
              font=font(21, custom_font), fill="#5b5c55")
    for column, name in enumerate(LABELS):
        draw.text((gutter + column * (cell_w + 12), 129), LABELS[name],
                  font=font(25, custom_font), fill="#202321")
    for row, sample in enumerate(samples):
        top = 180 + row * row_h
        draw.text((gutter, top), sample["title"] + "  ·  " + sample["purpose"],
                  font=font(21, custom_font), fill="#454942")
        for column, variant in enumerate(LABELS):
            with Image.open(output / f"{sample['id']}-{variant}.png") as img:
                thumb = ImageOps.contain(img.convert("RGB"), (cell_w, photo_h))
                x = gutter + column * (cell_w + 12) + (cell_w - thumb.width) // 2
                y = top + 44 + (photo_h - thumb.height) // 2
                sheet.paste(thumb, (x, y))
    draw.text((gutter, sheet.height - 64), "来源与许可见同目录 index.html；完整应用记录见每张结果旁的 JSON 文件。",
              font=font(19, custom_font), fill="#5b5c55")
    save_png(sheet, output / "contact-sheet.png")


def make_html(samples: list[dict], output: Path) -> None:
    cards = []
    for sample in samples:
        sid = sample["id"]
        title, purpose, author = [html.escape(sample[k]) for k in ("title", "purpose", "author")]
        cards.append(f'''<article>
<div class="card-heading"><h2>{title}</h2><p>{purpose}</p></div>
<div class="compare" id="{sid}" style="--split:50%">
  <img src="{sid}-before.png" alt="{title}，归一到 sRGB 的原图">
  <img class="after" src="{sid}-main.png" data-id="{sid}" alt="{title}，预设近似结果">
  <div class="divider"></div><span class="label left">原图</span><span class="label right result-label">主版 · 部分近似</span>
</div>
<label class="slider">拖动比较 <input type="range" min="0" max="100" value="50" aria-label="{title}前后对比" data-target="{sid}"></label>
<p class="credit">{author} · <a href="{html.escape(sample['source_url'], quote=True)}">来源</a> · <a href="{html.escape(sample['license_url'], quote=True)}">{html.escape(sample['license'])}</a></p>
<p class="files"><a href="{sid}-main.png">主版图片</a> · <a href="{sid}-grade.png">颜色分级图片</a> · <a href="{sid}-main.json">应用报告</a></p>
</article>''')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>预设试片 · LrC_XMP</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f3ed;color:#202321;font-family:system-ui,sans-serif;line-height:1.65}
main{max-width:1080px;margin:auto;padding:42px 22px 64px}h1{font-size:42px;line-height:1.2;margin:12px 0}h2{margin:0;font-size:23px}
.eyebrow{font-size:13px;letter-spacing:.15em;color:#637161}.intro{max-width:790px;color:#50584e}.notice{padding:14px 18px;border-left:3px solid #727660;background:#ebece2}
.controls{position:sticky;top:0;z-index:3;background:#f5f3edf5;padding:14px 0;display:flex;gap:10px;flex-wrap:wrap;backdrop-filter:blur(8px)}
button{padding:10px 16px;border:1px solid #ccd0c4;border-radius:30px;background:transparent;font:inherit;cursor:pointer}button[aria-pressed=true]{background:#343f36;color:white;border-color:#343f36}
article{background:#fff;border:1px solid #ddded5;border-radius:12px;margin:22px 0 36px;overflow:hidden}.card-heading{padding:20px 24px}.card-heading p{margin:5px 0 0;color:#697164}
.compare{position:relative;margin:auto;max-width:900px}.compare img{display:block;width:100%;height:auto}.compare .after{position:absolute;inset:0;clip-path:inset(0 0 0 var(--split))}
.divider{position:absolute;top:0;bottom:0;left:var(--split);width:2px;background:#fff;filter:drop-shadow(0 0 2px #333)}
.label{position:absolute;top:14px;padding:4px 10px;border-radius:4px;background:#172119cc;color:#fff;font-size:14px}.left{left:14px}.right{right:14px}
.slider{display:flex;align-items:center;gap:18px;padding:20px 24px}input[type=range]{flex:1;accent-color:#4d684c}.credit,.files{padding:0 24px;font-size:14px;color:#687163}.files{padding-bottom:12px}a{color:#355b3d;text-underline-offset:3px}
details{margin-top:22px}summary{cursor:pointer;font-weight:600}footer{color:#64705f;font-size:14px}@media(max-width:600px){h1{font-size:32px}main{padding:24px 14px}.card-heading,.slider{padding:16px}}
</style><main><div class="eyebrow">LRC_XMP / PYTHON PREVIEW</div><h1>预设试片</h1>
<p class="intro">温室、咖啡、人像与傍晚天空。切换预设，再拖动分界线比较同一张照片。页面和图片都可离线打开。</p>
<p class="notice">这些是 Python 的近似预览。主版有 32 项标量调整和 4 条曲线参与处理；8 项 RAW／Adobe 专属设置未应用。此页不能证明 Lightroom 的效果。</p>
<div class="controls"><button data-variant="main" aria-pressed="true">主版 · 部分近似</button><button data-variant="grade" aria-pressed="false">仅颜色分级 · 近似</button></div>
''' + "\n".join(cards) + '''
<details><summary>这次应用了什么</summary><p>主版使用原 XMP 的曝光、基础明暗、清晰度、曲线和 HSL 数值，以及颜色分级的色相、饱和度、混合和平衡。曲线保留原始锚点，插值与其他滑块使用本项目的近似模型。</p>
<p>未应用 Adobe Color、WhiteBalance、Temperature、Tint、ShadowTint、RedHue、GreenHue、BlueHue。完整方法见 <a href="../../docs/Python预览.md">Python 预览说明</a>。</p></details>
<footer><p>原始下载文件保留在本地。此处展示的是去除元数据、转为 sRGB 后的预览及调色版本；预设数值没有为这些照片重新调整。来源照片已渲染，含有作者原有的处理。</p></footer>
<script>
document.querySelectorAll('input[type=range]').forEach(input=>input.addEventListener('input',()=>document.getElementById(input.dataset.target).style.setProperty('--split',input.value+'%')));
document.querySelectorAll('button[data-variant]').forEach(button=>button.addEventListener('click',()=>{
document.querySelectorAll('button[data-variant]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
document.querySelectorAll('.after').forEach(img=>img.src=img.dataset.id+'-'+button.dataset.variant+'.png');
document.querySelectorAll('.result-label').forEach(label=>label.textContent=button.textContent);
}));
</script></main></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成带来源许可与应用报告的 XMP 试片。")
    parser.add_argument("--output", type=Path, default=ROOT / "examples/python-preview")
    parser.add_argument("--inputs", type=Path, default=ROOT / "local/inputs")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("预览目录已存在，请用 --output 指定新目录。")
    samples = json.loads((ROOT / "examples/sources.json").read_text())
    args.inputs.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda sample: fetch(sample, args.inputs), samples))
    args.output.mkdir(parents=True)
    reports = []
    for sample, path in zip(samples, paths):
        image, normalization = load_srgb(path)
        save_png(image, args.output / f"{sample['id']}-before.png")
        for variant, preset in PRESETS.items():
            report = preview(path, preset, args.output / f"{sample['id']}-{variant}.png", allow_partial=True)
            reports.append({"sample": sample["id"], "variant": variant,
                            "source_unchanged": report["source_files_unchanged"],
                            "coverage": report["coverage"]["counts"],
                            "mean_absolute_channel_difference": report["mean_absolute_channel_difference_0_to_1"]})
        print(sample["id"], normalization["preview_size"], "completed")
    make_html(samples, args.output)
    make_sheet(samples, args.output, args.font)
    (args.output / "summary.json").write_text(json.dumps({"adobe_equivalent": False, "renders": reports},
                                                       ensure_ascii=False, indent=2) + "\n")
    print("Gallery:", args.output / "index.html")


if __name__ == "__main__":
    main()
