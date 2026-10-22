"""Discover every repository preset; keep existing gallery URLs stable."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .preview import read_preset

ROOT = Path(__file__).resolve().parents[1]
KNOWN = {
    "confirmed/品川力仿色_原视频确认值_ProRAW.xmp": ("main", "品川力仿色 · 主版"),
    "partial/平川参考_仅已知颜色分级.xmp": ("grade", "仅颜色分级 · 简版"),
}


@dataclass(frozen=True)
class Variant:
    key: str
    name: str
    path: Path


def discover_presets(directory: Path = ROOT / "presets") -> list[Variant]:
    variants = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".xmp":
            continue
        relative = path.relative_to(directory).as_posix()
        preset = read_preset(path)
        key, name = KNOWN.get(relative, (
            "preset-" + hashlib.sha256(relative.encode()).hexdigest()[:16],
            preset.metadata.get("Name") or path.stem,
        ))
        variants.append(Variant(key, name, path))
    if not variants:
        raise ValueError("presets 目录中没有可用的 XMP。")
    return variants
