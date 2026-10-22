"""Apply all presets to an uploaded copy and return downloadable previews."""

import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from .catalog import Variant
from .preview import load_srgb, preview, save_png


def preview_all(data: bytes, suffix: str, variants: list[Variant]) -> dict:
    """This preview-only workflow explicitly allows reported unsupported fields."""
    if not data or len(data) > 25 * 1024 * 1024:
        raise ValueError("请选择一张 25 MB 以内的照片。")
    if suffix.lower() not in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}:
        raise ValueError("请选择 JPG、PNG、TIFF 或 WebP；HEIC、RAW／DNG 请先导出为 JPG。")
    if not variants:
        raise ValueError("没有可用预设。")
    results, errors = [], []
    with TemporaryDirectory(prefix="lrc-xmp-") as directory:
        work = Path(directory)
        source = work / ("photo" + suffix.lower())
        source.write_bytes(data)
        normalized, _ = load_srgb(source)
        save_png(normalized, work / "before.png")
        before = (work / "before.png").read_bytes()
        for index, variant in enumerate(variants):
            output = work / f"result-{index + 1}.png"
            try:
                report = preview(source, variant.path, output, allow_partial=True)
            except (ValueError, OSError) as error:
                errors.append({"name": variant.name, "error": str(error)})
                continue
            results.append({"key": variant.key, "name": variant.name,
                            "png": output.read_bytes(), "report": report})
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("before.png", before)
        for result in results:
            bundle.writestr(result["report"]["output"], result["png"])
            bundle.writestr(Path(result["report"]["output"]).with_suffix(".json").name,
                            json.dumps(result["report"], ensure_ascii=False, indent=2) + "\n")
        bundle.writestr("index.json", json.dumps({
            "adobe_equivalent": False,
            "results": [{"name": r["name"], "file": r["report"]["output"]} for r in results],
            "errors": errors,
        }, ensure_ascii=False, indent=2) + "\n")
        bundle.writestr("说明.txt", "Python 近似试色，长边最多 1200 像素。\n"
                         "before.png 为转成 sRGB 的原图预览。\n"
                         "XMP 原值未调整；每张结果的 JSON 列出实际参与及跳过的参数。\n"
                         "未验证 Lightroom 效果。\n")
    return {"before": before, "results": results, "errors": errors, "zip": archive.getvalue()}
