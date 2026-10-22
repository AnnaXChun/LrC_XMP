import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image
import pytest

from lrc_xmp.batch import preview_all
from lrc_xmp.catalog import ROOT, Variant, discover_presets


def image_bytes():
    rng = np.random.default_rng(42)
    buffer = io.BytesIO()
    Image.fromarray(rng.integers(0, 256, (40, 64, 3), dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_new_nested_preset_is_discovered_without_a_code_change(tmp_path):
    original = discover_presets()[0]
    nested = tmp_path / "studies"
    nested.mkdir()
    (nested / "a.XMP").write_bytes(original.path.read_bytes())
    (nested / "b.xmp").write_bytes(original.path.read_bytes())
    (nested / "ignore.source.json").write_text("{}")
    variants = discover_presets(tmp_path)
    assert len(variants) == 2
    assert len({v.key for v in variants}) == 2
    assert [v.key for v in variants] == [v.key for v in discover_presets(tmp_path)]


def test_batch_download_contains_every_render_and_verifiable_report():
    variants = discover_presets()
    source = image_bytes()
    hashes = {v.path: hashlib.sha256(v.path.read_bytes()).hexdigest() for v in variants}
    result = preview_all(source, ".png", variants)
    assert len(result["results"]) == len(variants)
    assert not result["errors"]
    with zipfile.ZipFile(io.BytesIO(result["zip"])) as archive:
        index = json.loads(archive.read("index.json"))
        assert len(index["results"]) == len(variants)
        for item in result["results"]:
            report = json.loads(archive.read(Path(item["report"]["output"]).with_suffix(".json").name))
            assert report["input_sha256"] == hashlib.sha256(source).hexdigest()
            assert report["output_sha256"] == hashlib.sha256(archive.read(report["output"])).hexdigest()
            assert report["source_files_unchanged"]
            assert not report["adobe_equivalent"]
            with Image.open(io.BytesIO(item["png"])) as image:
                assert image.size == (64, 40)
                assert image.info["icc_profile"]
                assert not image.getexif()
    assert hashes == {v.path: hashlib.sha256(v.path.read_bytes()).hexdigest() for v in variants}


def test_one_bad_preset_reports_failure_without_losing_other_results(tmp_path):
    variants = discover_presets()
    variants.insert(0, Variant("missing", "缺失文件", tmp_path / "missing.xmp"))
    result = preview_all(image_bytes(), ".png", variants)
    assert len(result["results"]) == len(variants) - 1
    assert result["errors"][0]["name"] == "缺失文件"


@pytest.mark.parametrize("data,suffix", [(b"", ".png"), (b"not an image", ".jpg"), (b"DNG", ".dng")])
def test_invalid_inputs_cannot_produce_misleading_results(data, suffix):
    with pytest.raises((ValueError, OSError)):
        preview_all(data, suffix, discover_presets())
