# Kotaemon 复习资料 RAG

基于 [Cinnamon/Kotaemon](https://github.com/Cinnamon/kotaemon) 的小组项目，当前完成了 PDF、PPTX、DOCX、Markdown 和 HTML 的文档入库验收。[上游 README](README.upstream.md) · [Apache-2.0 许可证](LICENSE.txt)

## 当前实现

1. **处理文档**时按格式读取内容，用 PDF 页码、PPT 幻灯片号或 Word 标题标记文档结构。PDF、PPTX 和 DOCX 中的图片文字由本地 OCR 提取，PDF 还保留页面预览。
2. **切块**时以页、幻灯片或章节为边界，保留来源位置。Word 原生表格单独成块，长表拆分后重复表头。
3. **建向量库**时把正文和表格分批送入百炼。Chroma 存向量，LanceDB 存切块和预览，SQLite 记录与源文件的关联。强制重建会清理旧记录。PDF 预览图只写入文档库。

## 模型配置

| 用途 | 当前配置 |
|---|---|
| LLM | DeepSeek Flash，模型 ID `deepseek-flash`，使用 DeepSeek 官方 API |
| Embedding | 阿里云百炼 `text-embedding-v4`，**2048 维**，每个同步请求最多 10 条 |

组员启动后，在应用的模型管理中填入自己的 API Key。百炼使用工作空间提供的 OpenAI 兼容地址。

## 入库验收

首轮跑通 13 份公开资料，修复后用 11 份真实资料复测，逐块核对了 **195 条 2048 维向量**。验收范围为文档处理、切块和向量写入。

| 样本 | 已验证的内容 | 正文／表格块与向量 |
|---|---|---:|
| UW《Hash Tables II》PDF | 第 25 页槽位与数值对应，第 26–28 页的分式、上标和因式 | 37 块、37 向量 |
| UW《Hash Tables II》PPTX | 37 张幻灯片，保留第 26–28 张的原生公式和证明文字 | 37 块、37 向量 |
| UTS Word 指南 | 截图中的 `No Spacing` 位于 `Headings` 章节 | 14 块、14 向量 |
| 上海理工大学教学大纲 | 7 张原生表格保留行列，合并单元格文字只保留一次 | 15 块、15 向量 |
| UTS PowerPoint 指南 | 第 4 张 `Smart Lookup`、第 17 张 `Banded Columns` | 25 块、25 向量 |
| 中科大 ClassIn PDF | 第 8 页正文和截图中的「试卷资源」「授权资源」 | 17 块、17 向量 |

UW PDF 强制重建后，旧的 74 条向量已清除，新库保留 37 条正文向量和 37 张可关联的页面预览。[复测明细](test-materials/ingestion-results.json) · [六份资料的测试问题与预期答案](test-materials/search-cases.md)

## 小组复测

在仓库根目录运行以下命令，需要 Python 3.10 和 `uv`。

```sh
uv sync --locked --package kotaemon --package ktem
uv run --no-sync python app.py
```

[自制测试文件 ZIP](test-materials/synthetic-samples.zip) 可直接下载。六份真实样本由原站下载，运行 `python test-materials/download_samples.py` 后，在 `downloads/real-samples/` 获得原稿，在 `downloads/real-samples.zip` 获得打包文件。

## 检索与问答交接

- **独立 Reranker 待接入并验收**。当前复测配置的 Cohere 重排未启用。可评估百炼 `qwen3-rerank`，并核对信息面板是否能区分缺失评分与有效零分。
- 已处理限定文件时的 Chroma 查询异常和 DeepSeek 引用请求的思考模式冲突。后续可用附带的六道题验收召回、证据定位及引用。
