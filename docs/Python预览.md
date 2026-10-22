# Python 预览

已经用现有两份 XMP 对四张测试照片生成了 **8 张调色结果**。可以打开 [离线对照页](../examples/python-preview/index.html)，切换预设并拖动分界线；GitHub 上可直接查看 [总览图](../examples/python-preview/contact-sheet.png)。

这次运行完全在本地完成，使用 Pillow、NumPy 和 SciPy，不需要 Adobe 授权。它是明确列出缺项的近似预览工具，尚未获得与 Lightroom 一致的渲染结果。

## 先看结果

| 场景 | 本次主版近似预览中看到的变化 |
| --- | --- |
| 温室植物 | 黄绿与绿色明显降饱和，整体更灰，白墙亮部收住 |
| 咖啡与白瓷杯 | 红橙色变柔，反光压低，暗部有抬升 |
| 人像与橙色衣服 | 橙色衣服降饱和，肤色也更灰，暂不适合当作肤色准确的结论 |
| 傍晚发射台 | 蓝色天空变得更灰，暖灯仍保留，画面对比变柔 |

仅颜色分级版的变化比主版轻。以上是对生成图的观察，没有根据效果反过来修改 XMP。原照片已经经过各自来源的渲染，也不是教程里的 iPhone ProRAW 原片。

## 开源工具怎么选

| 工具 | 检查结果 | 本次用途 |
| --- | --- | --- |
| [lightroom-py](https://github.com/drshy-org/lightroom-py) | 通过桥接控制 Lightroom，需要运行 Lightroom | 未采用 |
| [rawpy](https://github.com/letmaik/rawpy) | LibRaw 的 Python 接口，可解码 RAW；不会自动执行 Adobe XMP 的整个处理过程 | 本轮输入为已渲染图，未采用 |
| [PhotoS](https://github.com/Dongwu259/photo_s) | 有 XMP 导入与独立图像处理，但当前导入路径不完整 | 阅读源码后未用作本轮渲染器 |
| [Pillow](https://github.com/python-pillow/Pillow)、[NumPy](https://github.com/numpy/numpy)、[SciPy](https://github.com/scipy/scipy) | 图像读写、数组运算、曲线插值和高斯滤波 | 用来实现可检查的预览模型 |

PhotoS 检查固定在提交 `a7ced720fa876a3a45bf60425f6dbbddf9f1a92c`。其 [XMP 读取函数](https://github.com/Dongwu259/photo_s/blob/a7ced720fa876a3a45bf60425f6dbbddf9f1a92c/photo_s/lrxmp.py#L116) 主要读取属性，未读取本项目使用的曲线 `rdf:Seq`。其 [颜色分级映射](https://github.com/Dongwu259/photo_s/blob/a7ced720fa876a3a45bf60425f6dbbddf9f1a92c/photo_s/lrxmp.py#L400) 没有接入本 XMP 使用的阴影、高光 `SplitToning*` 字段及混合、平衡。[参数映射函数](https://github.com/Dongwu259/photo_s/blob/a7ced720fa876a3a45bf60425f6dbbddf9f1a92c/photo_s/lrxmp.py#L591) 也没有应用基础面板的高光、阴影、白色与黑色色阶。它的覆盖率分类不能直接当作实际应用证据。

本项目直接读取原 XMP，没有复制 PhotoS 代码。固定依赖版本及哈希保存在 `uv.lock`。

## 参数到底应用了多少

| 内容 | 主版 | 仅颜色分级版 | 解释 |
| --- | --- | --- | --- |
| 标量调整 | 32 项 | 8 项 | 数值原样读取，用独立模型近似渲染 |
| RGB 与分通道曲线 | 4 条、18 个锚点 | 无 | 所有锚点原样保留；插值方法可能不同于 Adobe |
| 未应用设置 | 8 项 | 无 | 每张结果旁的 JSON 都逐项列出 |
| 描述性字段 | `ToneCurveName2012=Custom` | 无 | 仅说明曲线类型，不额外改动像素 |

未应用的 8 项为：`CameraProfile`、`WhiteBalance`、`Temperature`、`Tint`、`ShadowTint`、`RedHue`、`GreenHue`、`BlueHue`。前四项依赖 RAW 白平衡及相机配置；后四项属于 Adobe 相机校准。预览器没有为它们猜一组替代数值。

所有未知字段同样进入跳过清单。存在跳过字段时，命令默认停止；只有显式指定 `--allow-partial` 才输出部分预览。模型内部对未给定控制使用中性起点，原 XMP 不补默认值。

## 近似模型

处理顺序固定为：sRGB 归一化、曝光、基础明暗、区域曲线、RGB 与分通道曲线、HSL、颜色分级、清晰度。该顺序是本预览器的定义，不代表 Lightroom 内部的处理顺序。

以下常数属于公开可查的项目实现选择，不是从教程提取的参数，也没有根据这四张照片调优。每个滑块原值仍保存在报告中。

| 调整 | 实现定义 | 与 Adobe 的差别 |
| --- | --- | --- |
| 曝光 | sRGB 反传递到线性光，乘以 `2^Exposure2012`，截到 0–1 后转回 sRGB | 已渲染图无法恢复 RAW 的高光余量 |
| 高光、阴影、白色、黑色 | 令 `y=0.2126R+0.7152G+0.0722B`；分别以 `y²`、`(1−y)²`、`y⁴`、`(1−y)⁴` 加权原值除以 100，再乘 `y(1−y)` 作为亮度增量 | 这是全局平滑权重，不能复现 Adobe 的局部适应明暗算法 |
| 区域曲线 | 四个亮度区域中心为 0.125、0.375、0.625、0.875；高斯宽度 0.18，权重归一化。加权滑块值除以 100，再乘 `0.5y(1−y)` | 原 XMP 未指定分割点；这里的固定区域只定义 Python 模型 |
| 点曲线 | 0–255 锚点归一化，用 SciPy PCHIP 插值；先整体 RGB，后红、绿、蓝 | 插值精确经过所有给定锚点，通道处理与 Adobe 的颜色空间仍可能不同 |
| HSL | 色相中心为 0°、30°、60°、120°、180°、240°、270°、300°，循环线性混合；色相原值乘 0.3°，饱和度乘 `1+原值/100`，亮度增量为 `0.25×原值/100×(1−abs(2L−1))` | 色域重叠、滑块灵敏度与 Adobe 不同 |
| 颜色分级 | 色相作为目标颜色，饱和度除以 100 作为强度。以 0.15、0.5、0.85 为三点中心；高斯宽度为 `0.15+0.20×Blending/100`，亮度位置移动 `0.3×Balance/100`，再以 soft-light 方式混合 | 混合、平衡实际参与运算，但权重与合成模型不是 Adobe 的实现 |
| 清晰度 | 高斯低通半径为长边的 0.008，至少 1 像素；高频亮度乘 `0.3×Clarity2012/100` | 简单局部对比模型；不等于 Adobe 清晰度 |

基础明暗、区域曲线和清晰度都将亮度差等量加到 RGB 三个通道，并在输出时限制到 0–1。PNG 输出附 sRGB ICC，去除 EXIF。未标记 ICC 的输入按 sRGB 处理，并在报告中注明。

## 重复运行

已在 macOS、Python 3.12.14 上运行。进入仓库后安装锁定依赖：

```bash
uv sync --locked
```

对自己的已渲染照片生成一张预览，输出必须使用新文件名：

```bash
uv run python -m lrc_xmp.preview photo.jpg \
  presets/confirmed/品川力仿色_原视频确认值_ProRAW.xmp \
  local/my-preview.png --allow-partial
```

运行完整试片流程，下载带哈希校验的样张，再生成新的对照目录：

```bash
uv run python -m lrc_xmp.demo --output local/preview-repeat
```

总览图需要中文字体。程序会查找系统字体；未找到时用 `--font` 指定一个 CJK 字体文件。已生成的对照页不依赖外部字体、脚本或服务器，下载完整仓库后即可离线打开。

输入当前支持不透明 RGB 或灰度 JPEG、PNG、TIFF、WebP，最长边默认缩至 1200 像素。RAW／DNG 会被明确拒绝，防止误把内嵌预览当作 RAW 解码结果。

## 验证记录

`uv run pytest -q` 的 10 项测试通过，覆盖了曲线完整读取、原值核对、未实现字段拦截、恒等行为、HSL 往返、曲线锚点、混合与平衡是否生效、极端像素、确定性和防覆盖。

四张照片的两份预设均已实际运行，输出和参数报告一一对应；输入照片及 XMP 的哈希保持不变。总览图已逐张查看。图片与离线页面的结果不构成 Lightroom 导入、面板显示或参数读回验证。

## 照片与许可

[样张清单](../examples/sources.json) 保存下载地址、SHA-256、署名、来源页和许可链接。Pexels 的温室照片由 Jovan Vasiljević 拍摄；咖啡照片由 Rachel Michetti 提供，许可为 CC0；人像来自 NASA，发射台照片来自 SpaceX，scikit-image 文档将后两者标为公有领域。

原始下载文件只保存在忽略的 `local/inputs/` 中。仓库里的样张是转为 sRGB、按需缩小、去除元数据后的对照版本。照片权利遵循各自来源许可，不因存入本仓库而改变。
