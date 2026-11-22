# Kotaemon 复习资料 RAG

基于 [Cinnamon/Kotaemon](https://github.com/Cinnamon/kotaemon) 的小组项目，当前完成了 PDF、PPTX、DOCX、Markdown 和 HTML 的文档入库验收。[上游 README](README.upstream.md) · [Apache-2.0 许可证](LICENSE.txt)

## 当前实现

1. **处理文档**时按格式读取内容，用 PDF 页码、PPT 幻灯片号或 Word 标题标记文档结构。PDF、PPTX 和 DOCX 中的图片文字由本地 OCR 提取，PDF 还保留页面预览。
2. **切块**时以页、幻灯片或章节为边界，保留来源位置。Word 原生表格单独成块，长表拆分后重复表头。
3. **建向量库**时把正文和表格分批送入百炼。Chroma 存向量，LanceDB 存切块和预览，SQLite 记录与源文件的关联。强制重建会清理旧记录。PDF 预览图只写入文档库。

## 模型配置

启动应用后进入 **Resources**。选择对应的供应商，在 **Specification** 中填写下表参数和自己的 `api_key`，勾选 **Set default** 后添加。

| 模型 | 应用路径与供应商 | Specification 参数 |
|---|---|---|
| LLM（DeepSeek Flash） | **Resources → LLMs → Add**，选 `ChatOpenAI` | `model: deepseek-flash`，`base_url: https://api.deepseek.com` |
| Embedding（阿里云百炼） | **Resources → Embeddings → Add**，选 `OpenAIEmbeddings` | `model: text-embedding-v4`，`dimensions: 2048`，`base_url` 填百炼工作空间提供的 OpenAI 兼容地址 |

## 入库验收

首轮跑通 13 份公开资料，修复后用 11 份真实资料复测，逐块核对了 **195 条 2048 维向量**。验收范围为文档处理、切块和向量写入。

| 样本 | 已验证的内容 | 正文／表格块与向量 |
|---|---|---:|
| [UW《Hash Tables II》PDF](https://courses.cs.washington.edu/courses/cse332/25sp/lecture/11-hash2.pdf) | 第 25 页槽位与数值对应，第 26–28 页的分式、上标和因式 | 37 块、37 向量 |
| [UW《Hash Tables II》PPTX](https://courses.cs.washington.edu/courses/cse332/25sp/lecture/11-hash2.pptx) | 37 张幻灯片，保留第 26–28 张的原生公式和证明文字 | 37 块、37 向量 |
| [UTS Word 指南 DOCX](https://wordpress-futures-prod.s3.ap-southeast-2.amazonaws.com/wp-content/uploads/2022/04/22132448/Microsoft-Word-document-example.docx) | 截图中的 `No Spacing` 位于 `Headings` 章节 | 14 块、14 向量 |
| [上海理工大学教学大纲 DOCX](https://oece.usst.edu.cn/_upload/article/files/63/b4/c131eafb4db2979754f132dbd3c1/5264fb92-3254-41d2-b973-8f191782d8c5.docx) | 7 张原生表格保留行列，合并单元格文字只保留一次 | 15 块、15 向量 |
| [UTS PowerPoint 指南 PPTX](https://wordpress-futures-prod.s3.ap-southeast-2.amazonaws.com/wp-content/uploads/2022/07/13093627/Accessible-content-practices-PPT-example-edited.pptx) | 第 4 张 `Smart Lookup`、第 17 张 `Banded Columns` | 25 块、25 向量 |
| [中科大 ClassIn PDF](https://www.teach.ustc.edu.cn/wp-content/uploads/2022/10/%E7%BA%BF%E4%B8%8A%E6%95%99%E5%AD%A6%E6%93%8D%E4%BD%9C%E8%AF%B4%E6%98%8E2022%E7%A7%8B-%E6%95%99%E5%B8%88%E7%80%9A%E6%B5%B7%E6%95%99%E5%AD%A6%E7%BD%91ClassIn.pdf) | 第 8 页正文和截图中的「试卷资源」「授权资源」 | 17 块、17 向量 |

## 小组复测

在仓库根目录运行以下命令，需要 Python 3.10 和 `uv`。

```sh
uv sync --locked --package kotaemon --package ktem
uv run --no-sync python app.py
```

[自制测试文件 ZIP](test-materials/synthetic-samples.zip) 可直接下载。六份真实样本由原站下载，运行 `python test-materials/download_samples.py` 后，在 `downloads/real-samples/` 获得原稿，在 `downloads/real-samples.zip` 获得打包文件。

[复测明细](test-materials/ingestion-results.json) · [六份资料的测试问题与预期答案](test-materials/search-cases.md)

## 检索与问答交接

- **独立 Reranker 待接入并验收**。当前复测配置的 Cohere 重排未启用。可评估百炼 `qwen3-rerank`，并核对信息面板是否能区分缺失评分与有效零分。
- 已处理限定文件时的 Chroma 查询异常和 DeepSeek 引用请求的思考模式冲突。后续可用附带的六道题验收召回、证据定位及引用。
