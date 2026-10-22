from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest
from lrc_xmp.catalog import discover_presets


def test_sample_button_runs_all_presets_and_changing_photo_hides_old_results():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    count = len(discover_presets())
    assert len(app.session_state["preview_result"][1]["results"]) == count
    assert len(app.get("image")) == count + 1
    assert len(app.get("download_button")) == count + 1
    app.selectbox[0].set_value(1).run()
    assert not app.exception
    assert not app.success
    assert not app.get("download_button")
