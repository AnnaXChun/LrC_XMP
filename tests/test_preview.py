from pathlib import Path
import json

import numpy as np
from PIL import Image
import pytest

from lrc_xmp.preview import (Preset, coverage, grade_weights, hsl_to_rgb, point_curve,
                             preview, read_preset, render, rgb_to_hsl, sha256)

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "presets/confirmed/品川力仿色_原视频确认值_ProRAW.xmp"
PARTIAL = ROOT / "presets/partial/平川参考_仅已知颜色分级.xmp"


def test_source_values_and_all_rdf_curve_points_survive_import():
    source = json.loads(MAIN.with_suffix(".source.json").read_text())
    preset = read_preset(MAIN)
    assert preset.scalars == source["expected_scalar_settings"]
    assert preset.curves == source["expected_curves"]
    assert sum(map(len, preset.curves.values())) == 18
    assert coverage(preset)["counts"] == {
        "approximate": 32, "anchors_preserved_interpolation_approximate": 4,
        "skipped": 8, "descriptive": 1,
    }


def test_partial_grade_preserves_all_eight_values():
    preset = read_preset(PARTIAL)
    assert len(preset.scalars) == 8
    assert coverage(preset)["counts"]["skipped"] == 0
    assert preset.scalars == {k: read_preset(MAIN).scalars[k] for k in preset.scalars}


def test_unsupported_fields_require_explicit_opt_in():
    pixels = np.full((10, 10, 3), 0.5)
    with pytest.raises(ValueError, match="allow-partial"):
        render(pixels, read_preset(MAIN))
    unknown = Preset({"FutureAdjustment": "42"}, {}, {})
    with pytest.raises(ValueError, match="FutureAdjustment"):
        render(pixels, unknown)
    assert coverage(unknown)["fields"]["FutureAdjustment"]["status"] == "skipped"


def test_empty_and_zero_edits_are_identity():
    rgb = np.random.default_rng(13).random((20, 30, 3))
    np.testing.assert_array_equal(render(rgb, Preset({}, {}, {})), rgb)
    zero = Preset({"SplitToningShadowSaturation": "0", "SplitToningShadowHue": "156",
                   "HueAdjustmentGreen": "0", "Clarity2012": "0"}, {}, {})
    np.testing.assert_allclose(render(rgb, zero), rgb, atol=1e-14)


def test_hsl_roundtrip_and_gray_stability():
    rgb = np.concatenate([np.random.default_rng(9).random((12, 3)),
                          np.eye(3), np.array([[0, 0, 0], [1, 1, 1], [.5, .5, .5]])])
    np.testing.assert_allclose(hsl_to_rgb(*rgb_to_hsl(rgb)), rgb, atol=1e-14)


def test_interpolation_passes_through_every_original_anchor():
    for points in read_preset(MAIN).curves.values():
        anchors = np.asarray(points) / 255
        np.testing.assert_allclose(point_curve(anchors[:, 0], points), anchors[:, 1], atol=1e-14)


def test_balance_and_blending_have_actual_effects():
    y = np.linspace(0, 1, 128)
    low = grade_weights(y, 100, -100)
    high = grade_weights(y, 100, 100)
    assert high[:, 2].mean() > low[:, 2].mean()
    assert not np.allclose(grade_weights(y, 0, 0), grade_weights(y, 100, 0))
    np.testing.assert_allclose(high.sum(axis=-1), 1)


def test_extremes_finite_deterministic_and_do_not_mutate_input():
    rgb = np.array([[[0., 0., 0.], [1., 1., 1.], [1., 0., 0.], [.1, .8, .2]]])
    before = rgb.copy()
    preset = read_preset(MAIN)
    a = render(rgb, preset, allow_partial=True)
    b = render(rgb, preset, allow_partial=True)
    assert np.isfinite(a).all() and a.min() >= 0 and a.max() <= 1
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(rgb, before)
    assert not np.allclose(a, before)


def test_files_are_preserved_and_reports_match_the_output(tmp_path):
    source = tmp_path / "input.png"
    Image.new("RGB", (24, 32), (120, 80, 60)).save(source)
    before = sha256(source), sha256(MAIN)
    output = tmp_path / "result.png"
    report = preview(source, MAIN, output, allow_partial=True)
    assert before == (sha256(source), sha256(MAIN))
    assert report["source_files_unchanged"] is True
    assert report["output_sha256"] == sha256(output)
    assert report["adobe_equivalent"] is False
    with pytest.raises(FileExistsError):
        preview(source, MAIN, output, allow_partial=True)
    with pytest.raises(ValueError, match="覆盖"):
        preview(source, MAIN, source, allow_partial=True)


def test_duplicate_or_malformed_curve_is_rejected(tmp_path):
    bad = tmp_path / "bad.xmp"
    bad.write_text(MAIN.read_text().replace("42, 53", "0, 53"))
    with pytest.raises(ValueError, match="递增"):
        read_preset(bad)
