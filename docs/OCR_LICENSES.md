# 本地 OCR 的分发与许可记录

2026-10-11在Windows amd64 / Python3.13中安装并校验：RapidOCR3.10.0（Apache-2.0）、ONNX Runtime1.31.0 CPU（MIT）。新增依赖锁定于 `backend/requirements-ocr.txt`，现有通用依赖仍由 `backend/requirements.txt` 提供。

RapidOCR工程版权属于RapidOCR Authors；内置模型版权属于Baidu及相应PaddleOCR权利人，RapidAI负责转换与分发，两者都使用Apache-2.0但属于不同作品。模型清单、源链接和实际SHA256在 `backend/data/ocr_models.json`。模型来源说明：[RapidOCR官方模型许可记录](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/)。

保存安装wheel内的完整 `LICENSE`、`MODEL_LICENSES.md`；ONNX Runtime完整许可和第三方声明亦保存在 `docs/licenses/`，保留原内容。源包只包含代码、锁文件与许可记录，不包含venv、OCR权重或ONNX二进制。安装时下载原wheel；部署若分发依赖或模型，须同时保留其许可、署名与第三方声明，不能把本项目MIT许可当作所有依赖的许可。

其他OCR增量依赖的上游许可应随其wheel保留：NumPy（BSD）、OpenCV（Apache-2.0及第三方代码声明）、Pillow（HPND）、Shapely（BSD及GEOS LGPL）、pyclipper（MIT/Boost）、OmegaConf（BSD）、PyYAML（MIT）、six（MIT）、tqdm（MPL/MIT）、colorlog（MIT）、flatbuffers（Apache-2.0）、protobuf（BSD）。准确完整条款以安装分发中的许可证为准，本表不能替代原文。

识别验收图片是本项目原创测试标签，明确标注“SAMPLE LABEL/非真实商品”，不使用真实包装、机构图表或商品商标。生成脚本仅借用本机字体渲染文字，字体文件不随源码交付；已有PNG可以直接测试。
