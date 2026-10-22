import json
from pathlib import Path

import numpy as np
import pytest

from lrc_xmp.catalog import ROOT, discover_presets
from lrc_xmp.preview import Preset, coverage, read_preset, render, sha256


@pytest.mark.parametrize("path", sorted((ROOT / "presets/photographers").rglob("*.xmp")))
def test_author_files_match_published_archive_hash_and_all_recorded_values(path):
    source = json.loads(path.with_suffix(".source.json").read_text())
    preset = read_preset(path)
    assert source["source"]["type"] == "photographer_published_original_file"
    assert sha256(path) == source["source"]["original_file_sha256"]
    assert preset.scalars == source["expected_scalar_settings"]
    assert preset.curves == source["expected_curves"]
    assert preset.metadata == source["expected_metadata"]
    # A profile container with attributes must survive parsing even without children.
    assert "Name" in preset.scalars["Look"]
    assert coverage(preset)["fields"]["Look"]["status"] == "skipped"


def test_default_catalog_has_no_project_authored_studies():
    for variant in discover_presets():
        source = json.loads(variant.path.with_suffix(".source.json").read_text())
        assert source["source"].get("type") != "project_authored_style_study"
        assert "studies" not in variant.path.parts


def test_grayscale_switch_and_mixer_preserve_neutral_pixels():
    rgb = np.array([[[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.4, 0.4, 0.4]]])
    plain = render(rgb, Preset({"ConvertToGrayscale": "True"}, {}, {}))
    mixed = render(rgb, Preset({"ConvertToGrayscale": "True", "GrayMixerRed": "50"}, {}, {}))
    assert np.allclose(mixed[..., 0], mixed[..., 1])
    assert np.allclose(mixed[..., 1], mixed[..., 2])
    assert mixed[0, 0, 0] > plain[0, 0, 0]
    assert np.allclose(mixed[0, 1:], plain[0, 1:])
    assert np.array_equal(rgb, render(rgb, Preset({"ConvertToGrayscale": "False"}, {}, {})))


def test_contrast_saturation_and_parametric_splits_affect_their_targets():
    gray = np.repeat(np.array([0.2, 0.4, 0.6, 0.8])[None, :, None], 3, axis=-1)
    contrast = render(gray, Preset({"Contrast2012": "50"}, {}, {}))
    assert contrast[0, 0, 0] < gray[0, 0, 0]
    assert contrast[0, -1, 0] > gray[0, -1, 0]
    color = np.array([[[0.7, 0.2, 0.1]]])
    desaturated = render(color, Preset({"Saturation": "-100"}, {}, {}))
    assert np.allclose(desaturated[..., 0], desaturated[..., 2])
    original = render(gray, Preset({"ParametricDarks": "-80"}, {}, {}))
    shifted = render(gray, Preset({"ParametricDarks": "-80", "ParametricMidtoneSplit": "65"}, {}, {}))
    assert not np.allclose(original, shifted)


@pytest.mark.parametrize("settings", [
    'crs:ConvertToGrayscale="sometimes"',
    'crs:ParametricShadowSplit="70" crs:ParametricMidtoneSplit="20"',
])
def test_invalid_author_controls_fail_explicitly(tmp_path, settings):
    path = tmp_path / "invalid.xmp"
    path.write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                    '<rdf:Description xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/" '
                    + settings + '/></rdf:RDF></x:xmpmeta>')
    with pytest.raises(ValueError):
        read_preset(path)
