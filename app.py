"""Local Streamlit photo preview UI. Run: uv run --extra ui streamlit run app.py."""

import hashlib
import json
from pathlib import Path

import streamlit as st

from lrc_xmp.batch import preview_all
from lrc_xmp.catalog import ROOT, discover_presets

st.set_page_config(page_title="LrC_XMP · 一键试色", page_icon="🎞️", layout="wide")
st.title("选张照片，一键找到喜欢的色调。")
st.write("试遍全部预设，把原图和效果放在一起看，再下载喜欢的版本。照片在本机处理。")
st.caption("Python 近似试色 · 无需 Adobe 账号 · 长边最多 1200 像素")

variants = discover_presets()
samples = json.loads((ROOT / "examples/sources.json").read_text(encoding="utf-8"))
uploaded = st.file_uploader("放入自己的照片", type=["jpg", "jpeg", "png", "tif", "tiff", "webp"])
if uploaded is None:
    sample_id = st.selectbox("也可以先用样张试试", range(len(samples)),
                             format_func=lambda i: samples[i]["title"])
    sample = samples[sample_id]
    data = (ROOT / "examples/python-preview" / f"{sample['id']}-before.png").read_bytes()
    suffix = ".png"
    st.caption(f"样张：{sample['author']} · [{sample['license']}]({sample['license_url']})")
else:
    data, suffix = uploaded.getvalue(), Path(uploaded.name).suffix

st.info("这里展示 Python 近似效果。各款的相机配置、RAW 白平衡、颗粒等缺项见处理报告。"
        "原件中的固定曝光会照常应用，部分照片可能过亮。HEIC、RAW／DNG 请先导出为 JPG。")
source_key = hashlib.sha256(data + suffix.encode()).hexdigest()
if st.button(f"一键试遍全部 {len(variants)} 个预设", type="primary"):
    st.session_state.pop("preview_result", None)
    try:
        with st.spinner("正在逐个试色…"):
            outcome = preview_all(data, suffix, variants)
        st.session_state.preview_result = (source_key, outcome)
    except (ValueError, OSError) as error:
        st.error(str(error))

stored = st.session_state.get("preview_result")
if stored and stored[0] == source_key:
    outcome = stored[1]
    if outcome["results"]:
        st.success(f"已生成 {len(outcome['results'])} 个版本，可以并排比较了。")
        st.download_button("打包下载全部结果", outcome["zip"], "LrC_XMP-previews.zip", "application/zip")
    for error in outcome["errors"]:
        st.error(f"{error['name']} 未生成：{error['error']}")
    # Use explicit rows so different photo/caption heights cannot mix versions.
    cards = [{"name": "原图", "png": outcome["before"]}, *outcome["results"]]
    for start in range(0, len(cards), 3):
        for column, result in zip(st.columns(3), cards[start:start + 3]):
            with column:
                st.subheader(result["name"])
                st.image(result["png"], width="stretch")
                if "key" in result:
                    st.download_button("下载这张", result["png"], f"{result['key']}.png", "image/png", key=result["key"])
    with st.expander("查看处理记录"):
        st.write("所有版本共用同一张原图。文件参数原样读取，每份报告都列出跳过的设置。")
        for result in outcome["results"]:
            st.write(result["name"])
            st.json(result["report"], expanded=False)
else:
    st.write("选好照片后，点击上方按钮。")
