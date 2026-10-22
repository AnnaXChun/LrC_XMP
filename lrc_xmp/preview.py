"""Read original XMP values and render an explicitly partial sRGB preview.

The approximation equations are documented in docs/Python预览.md.
RAW white balance, Adobe profiles and camera calibration are never simulated.
"""

from __future__ import annotations

import argparse
import colorsys
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageCms, ImageOps
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter

from . import __version__

CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS = {"crs": CRS, "rdf": RDF}
META = {
    "PresetType", "UUID", "SupportsAmount", "SupportsColor",
    "SupportsMonochrome", "SupportsSceneReferred", "SupportsOutputReferred",
    "HasSettings", "Name", "Group", "Description",
    "Cluster", "ShortName", "SortName", "Copyright", "ContactInfo", "Version",
    "CameraModelRestriction", "SupportsHighDynamicRange", "SupportsNormalDynamicRange",
}
CURVES = ("ToneCurvePV2012", "ToneCurvePV2012Red", "ToneCurvePV2012Green",
          "ToneCurvePV2012Blue")
COLORS = ("Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta")
CENTERS = np.array([0, 30, 60, 120, 180, 240, 270, 300, 360], dtype=float)
BASIC = ("Shadows2012", "Blacks2012", "Highlights2012", "Whites2012")
PARAMETRIC = ("ParametricShadows", "ParametricDarks", "ParametricLights", "ParametricHighlights")
PARAMETRIC_SPLITS = ("ParametricShadowSplit", "ParametricMidtoneSplit", "ParametricHighlightSplit")
GRADING = (
    "SplitToningShadowHue", "SplitToningShadowSaturation",
    "ColorGradeMidtoneHue", "ColorGradeMidtoneSat",
    "SplitToningHighlightHue", "SplitToningHighlightSaturation",
    "ColorGradeBlending", "SplitToningBalance",
)
SKIPPED = {
    "CameraProfile": "Adobe Color profile and Adobe RAW pipeline are unavailable.",
    "WhiteBalance": "RAW white balance mode cannot be applied to an already rendered sRGB image.",
    "Temperature": "Absolute RAW Kelvin requires source camera/WB data; no guessed sRGB correction.",
    "Tint": "RAW tint mapping is unavailable; no guessed sRGB correction.",
    "ShadowTint": "Adobe camera calibration is not implemented.",
    "RedHue": "Adobe camera calibration is not implemented.",
    "GreenHue": "Adobe camera calibration is not implemented.",
    "BlueHue": "Adobe camera calibration is not implemented.",
}


@dataclass
class Preset:
    scalars: dict[str, str]
    curves: dict[str, list[list[int]]]
    metadata: dict[str, str]

    def value(self, key: str, default: float = 0.0) -> float:
        return float(self.scalars.get(key, default))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_preset(path: Path) -> Preset:
    text = path.read_text(encoding="utf-8")
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("不接受包含 DTD 或实体声明的 XMP。")
    root = ET.fromstring(text)
    descriptions = root.findall(".//rdf:Description", NS)
    if len(descriptions) != 1:
        raise ValueError("预览器只支持一个 rdf:Description，避免误合并局部设置。")
    desc = descriptions[0]
    scalars = {k.removeprefix(f"{{{CRS}}}"): v for k, v in desc.attrib.items()
               if k.startswith(f"{{{CRS}}}")}
    curves = {}
    for child in desc:
        if not child.tag.startswith(f"{{{CRS}}}"):
            raise ValueError(f"不支持的命名空间：{child.tag}")
        key = child.tag.removeprefix(f"{{{CRS}}}")
        if key in scalars:
            raise ValueError(f"重复字段：{key}")
        if key in CURVES:
            points = [[int(v.strip()) for v in (li.text or "").split(",")]
                      for li in child.findall("rdf:Seq/rdf:li", NS)]
            if len(points) < 2 or any(len(p) != 2 for p in points):
                raise ValueError(f"曲线缺少有效锚点：{key}")
            xs = [p[0] for p in points]
            if xs[0] != 0 or xs[-1] != 255 or any(a >= b for a, b in zip(xs, xs[1:])):
                raise ValueError(f"曲线横坐标必须从 0 到 255 严格递增：{key}")
            if any(v < 0 or v > 255 for p in points for v in p):
                raise ValueError(f"曲线锚点超出 0–255：{key}")
            curves[key] = points
        elif (len(child) or child.attrib) and key not in META:
            # Keep unimplemented structures visible in the coverage report.
            scalars[key] = ET.tostring(child, encoding="unicode")
        else:
            scalars[key] = "".join(child.itertext()).strip()
    metadata = {k: scalars.pop(k) for k in tuple(scalars) if k in META}
    preset = Preset(scalars, curves, metadata)
    for key, value in scalars.items():
        if method_for(key) == "approximate":
            if key == "ConvertToGrayscale":
                if value not in {"True", "False"}:
                    raise ValueError("ConvertToGrayscale 必须为 True 或 False。")
                continue
            try:
                number = float(value)
            except ValueError as error:
                raise ValueError(f"参数不是数字：{key}") from error
            if not np.isfinite(number):
                raise ValueError(f"参数不是有限值：{key}")
            low, high = (-100, 100)
            if key.endswith("Hue") and key in GRADING:
                low, high = (0, 360)
            elif key.endswith(("Saturation", "Sat")) and key in GRADING:
                low, high = (0, 100)
            elif key == "ColorGradeBlending" or key in PARAMETRIC_SPLITS:
                low, high = (0, 100)
            elif key == "Exposure2012":
                low, high = (-5, 5)
            if not low <= number <= high:
                raise ValueError(f"参数超出支持范围：{key}={value}")
    splits = [preset.value(key, default) for key, default in zip(PARAMETRIC_SPLITS, (25, 50, 75))]
    if not 0 < splits[0] < splits[1] < splits[2] < 100:
        raise ValueError("区域曲线的三个分割点必须在 0–100 内严格递增。")
    return preset


def method_for(key: str) -> str:
    if key == "ToneCurveName2012":
        return "descriptive"
    supported = {*BASIC, *PARAMETRIC, *PARAMETRIC_SPLITS, *GRADING,
                 "Exposure2012", "Clarity2012", "Contrast2012", "Saturation",
                 "Vibrance", "ConvertToGrayscale"}
    supported.update(prefix + color for prefix in
                     ("HueAdjustment", "SaturationAdjustment", "LuminanceAdjustment", "GrayMixer")
                     for color in COLORS)
    return "approximate" if key in supported else "skipped"


def coverage(preset: Preset) -> dict:
    fields = {key: {"value": value, "status": method_for(key)}
              for key, value in preset.scalars.items()}
    for key, field in fields.items():
        if field["status"] == "skipped":
            field["reason"] = SKIPPED.get(key, "Unsupported setting; never silently applied.")
    for key, points in preset.curves.items():
        fields[key] = {"value": points, "status": "anchors_preserved_interpolation_approximate"}
    counts = {status: sum(v["status"] == status for v in fields.values()) for status in
              ("approximate", "anchors_preserved_interpolation_approximate", "skipped", "descriptive")}
    return {"counts": counts, "fields": fields}


def load_srgb(path: Path, max_edge: int = 1200) -> tuple[Image.Image, dict]:
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        raise ValueError("输入仅支持已渲染的照片；不接受 RAW／DNG。")
    with Image.open(path) as source:
        if source.mode not in {"RGB", "L"}:
            raise ValueError("当前预览器只处理不透明的 RGB 或灰度照片。")
        icc = source.info.get("icc_profile")
        img = ImageOps.exif_transpose(source).convert("RGB")
        if icc:
            img = ImageCms.profileToProfile(img, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                            ImageCms.createProfile("sRGB"), outputMode="RGB")
        original_size = list(img.size)
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        img.info.clear()
    return img, {"input_color_handling": "embedded ICC converted to sRGB" if icc else "untagged; assumed sRGB",
                 "source_size": original_size, "preview_size": list(img.size),
                 "exif_orientation_normalized": True, "metadata_removed": True}


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.2126, 0.7152, 0.0722])


def replace_luma(rgb: np.ndarray, target: np.ndarray) -> np.ndarray:
    # Add the same delta to all channels; avoid unstable division near black.
    return np.clip(rgb + (target - luminance(rgb))[..., None], 0, 1)


def expose(rgb: np.ndarray, ev: float) -> np.ndarray:
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    linear = np.clip(linear * 2 ** ev, 0, 1)
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - 0.055)


def point_curve(values: np.ndarray, points: list[list[int]]) -> np.ndarray:
    p = np.asarray(points, dtype=float) / 255
    return np.clip(PchipInterpolator(p[:, 0], p[:, 1])(np.clip(values, 0, 1)), 0, 1)


def rgb_to_hsl(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hi, lo = rgb.max(axis=-1), rgb.min(axis=-1)
    delta = hi - lo
    light = (hi + lo) / 2
    sat = np.divide(delta, 1 - np.abs(2 * light - 1), out=np.zeros_like(light),
                    where=(delta > 1e-12))
    safe = np.where(delta > 1e-12, delta, 1)
    r, g, b = np.moveaxis(rgb, -1, 0)
    index = rgb.argmax(axis=-1)
    hue = np.select([index == 0, index == 1], [((g - b) / safe) % 6, (b - r) / safe + 2],
                    default=(r - g) / safe + 4) / 6
    return np.where(delta > 1e-12, hue, 0), sat, light


def hsl_to_rgb(hue: np.ndarray, sat: np.ndarray, light: np.ndarray) -> np.ndarray:
    def channel(n: int) -> np.ndarray:
        k = (n + hue * 12) % 12
        return light - sat * np.minimum(light, 1 - light) * np.maximum(-1, np.minimum(np.minimum(k - 3, 9 - k), 1))
    return np.stack([channel(0), channel(8), channel(4)], axis=-1)


def apply_hsl(rgb: np.ndarray, preset: Preset) -> np.ndarray:
    h, s, l = rgb_to_hsl(rgb)
    original_h = h * 360
    adjustments = []
    for prefix in ("HueAdjustment", "SaturationAdjustment", "LuminanceAdjustment"):
        values = [preset.value(prefix + c) / 100 for c in COLORS]
        adjustments.append(np.interp(original_h, CENTERS, values + values[:1]))
    h = (h + adjustments[0] * (30 / 360)) % 1
    s = np.clip(s * (1 + adjustments[1]), 0, 1)
    l = np.clip(l + 0.25 * adjustments[2] * (1 - np.abs(2 * l - 1)), 0, 1)
    return hsl_to_rgb(h, s, l)


def grade_weights(y: np.ndarray, blending: float, balance: float) -> np.ndarray:
    shifted = np.clip(y + balance / 100 * 0.3, 0, 1)
    sigma = 0.15 + blending / 100 * 0.20
    weights = np.exp(-0.5 * ((shifted[..., None] - [0.15, 0.5, 0.85]) / sigma) ** 2)
    return weights / weights.sum(axis=-1, keepdims=True)


def apply_grading(rgb: np.ndarray, preset: Preset) -> np.ndarray:
    weights = grade_weights(luminance(rgb), preset.value("ColorGradeBlending", 50),
                            preset.value("SplitToningBalance"))
    tint = np.full_like(rgb, 0.5)
    for i, (hue_key, sat_key) in enumerate(zip(GRADING[:6:2], GRADING[1:6:2])):
        hue = preset.value(hue_key) / 360
        strength = preset.value(sat_key) / 100
        color = np.array(colorsys.hsv_to_rgb(hue, 1, 1))
        tint += weights[..., i, None] * strength * (color - 0.5)
    # Standard soft-light compositing; no claim of Adobe's grading model.
    d = np.where(rgb <= 0.25, ((16 * rgb - 12) * rgb + 4) * rgb, np.sqrt(rgb))
    out = np.where(tint <= 0.5, rgb - (1 - 2 * tint) * rgb * (1 - rgb),
                   rgb + (2 * tint - 1) * (d - rgb))
    return np.clip(out, 0, 1)


def render(rgb: np.ndarray, preset: Preset, *, allow_partial: bool = False) -> np.ndarray:
    report = coverage(preset)
    if report["counts"]["skipped"] and not allow_partial:
        keys = [k for k, v in report["fields"].items() if v["status"] == "skipped"]
        raise ValueError("存在未实现字段；显式添加 --allow-partial 才能生成部分预览：" + ", ".join(keys))
    if rgb.ndim != 3 or rgb.shape[-1] != 3 or not np.isfinite(rgb).all() or np.any((rgb < 0) | (rgb > 1)):
        raise ValueError("图像必须是有限的 0–1 RGB 数组。")
    out = np.array(rgb, dtype=np.float64, copy=True)
    if "Exposure2012" in preset.scalars:
        out = expose(out, preset.value("Exposure2012"))
    if "Contrast2012" in preset.scalars:
        y = luminance(out)
        # Midpoint-pivoted contrast, intentionally independent of Adobe's model.
        out = replace_luma(out, np.clip(0.5 + (y - 0.5) * (1 + preset.value("Contrast2012") / 100), 0, 1))
    if any(k in preset.scalars for k in BASIC):
        y = luminance(out)
        masks = [(1 - y) ** 2, (1 - y) ** 4, y ** 2, y ** 4]
        shift = sum(preset.value(k) / 100 * m for k, m in zip(BASIC, masks))
        out = replace_luma(out, np.clip(y + shift * y * (1 - y), 0, 1))
    if any(k in preset.scalars for k in PARAMETRIC):
        y = luminance(out)
        edges = np.array([0, *[preset.value(k, d) / 100 for k, d in
                               zip(PARAMETRIC_SPLITS, (25, 50, 75))], 1])
        centers = (edges[:-1] + edges[1:]) / 2
        weights = np.exp(-0.5 * ((y[..., None] - centers) / 0.18) ** 2)
        weights /= weights.sum(axis=-1, keepdims=True)
        shift = weights @ np.array([preset.value(k) / 100 for k in PARAMETRIC])
        out = replace_luma(out, np.clip(y + 0.5 * shift * y * (1 - y), 0, 1))
    if CURVES[0] in preset.curves:
        out = point_curve(out, preset.curves[CURVES[0]])
    for channel, key in enumerate(CURVES[1:]):
        if key in preset.curves:
            out[..., channel] = point_curve(out[..., channel], preset.curves[key])
    if any(k.startswith(("HueAdjustment", "SaturationAdjustment", "LuminanceAdjustment")) for k in preset.scalars):
        out = apply_hsl(out, preset)
    if any(k in preset.scalars for k in ("Saturation", "Vibrance")):
        h, s, l = rgb_to_hsl(out)
        s = np.clip(s * (1 + preset.value("Saturation") / 100), 0, 1)
        s = np.clip(s * (1 + preset.value("Vibrance") / 100 * (1 - s)), 0, 1)
        out = hsl_to_rgb(h, s, l)
    if preset.scalars.get("ConvertToGrayscale") == "True":
        h, s, _ = rgb_to_hsl(out)
        values = [preset.value("GrayMixer" + color) / 100 for color in COLORS]
        shift = np.interp(h * 360, CENTERS, values + values[:1])
        y = np.clip(luminance(out) + 0.25 * shift * s, 0, 1)
        out = np.repeat(y[..., None], 3, axis=-1)
    if any(k in preset.scalars for k in GRADING):
        out = apply_grading(out, preset)
    if "Clarity2012" in preset.scalars:
        y = luminance(out)
        blur = gaussian_filter(y, sigma=max(1, max(out.shape[:2]) * 0.008))
        out = replace_luma(out, np.clip(y + 0.3 * preset.value("Clarity2012") / 100 * (y - blur), 0, 1))
    if not np.isfinite(out).all():
        raise ValueError("渲染产生非有限值。")
    return np.clip(out, 0, 1)


def save_png(image: Image.Image, path: Path) -> None:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        image.save(stream, format="PNG", icc_profile=profile)


def preview(input_path: Path, preset_path: Path, output_path: Path, *, allow_partial: bool = False,
            max_edge: int = 1200) -> dict:
    if max_edge < 16 or max_edge > 4096:
        raise ValueError("预览长边需在 16–4096 像素之间。")
    report_path = output_path.with_suffix(".json")
    if output_path.suffix.lower() != ".png":
        raise ValueError("输出使用 PNG，避免额外的有损压缩。")
    if any(p.resolve() in {input_path.resolve(), preset_path.resolve()} for p in (output_path, report_path)):
        raise ValueError("输出不能覆盖输入照片或 XMP。")
    if output_path.exists() or report_path.exists():
        raise FileExistsError("输出或报告已存在，请换一个名称。")
    source_hash, preset_hash = sha256(input_path), sha256(preset_path)
    preset = read_preset(preset_path)
    image, normalization = load_srgb(input_path, max_edge)
    before = np.asarray(image, dtype=np.float64) / 255
    after = render(before, preset, allow_partial=allow_partial)
    quantized = np.rint(after * 255).astype(np.uint8)
    save_png(Image.fromarray(quantized), output_path)
    report = {"renderer": "lrc-xmp-preview", "renderer_version": __version__,
              "adobe_equivalent": False, "lightroom_runtime_verified": False,
              "input": input_path.name, "input_sha256": source_hash,
              "preset": preset_path.name, "preset_sha256": preset_hash,
              "output": output_path.name, "output_sha256": sha256(output_path),
              "normalization": normalization, "coverage": coverage(preset),
              "mean_absolute_channel_difference_0_to_1": float(np.abs(after - before).mean()),
              "before_mean_rgb": before.mean(axis=(0, 1)).tolist(),
              "after_mean_rgb": after.mean(axis=(0, 1)).tolist(),
              "source_files_unchanged": source_hash == sha256(input_path) and preset_hash == sha256(preset_path)}
    if not report["source_files_unchanged"]:
        raise RuntimeError("输入照片或预设在执行期间发生变化。")
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="XMP 的 Python 近似预览，不能替代 Lightroom 验证。")
    parser.add_argument("input", type=Path)
    parser.add_argument("preset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--allow-partial", action="store_true", help="允许跳过报告中明确列出的未实现字段")
    parser.add_argument("--max-edge", type=int, default=1200)
    args = parser.parse_args()
    report = preview(args.input, args.preset, args.output, allow_partial=args.allow_partial, max_edge=args.max_edge)
    print(json.dumps({"output": report["output"], "coverage": report["coverage"]["counts"],
                      "adobe_equivalent": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
