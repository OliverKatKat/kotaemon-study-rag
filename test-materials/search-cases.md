# 六份真实资料的搜索验收

每次只选中对应文件。回答覆盖下表要点，证据切块也能定位到指定页、幻灯片或章节时，记为通过。这些是检索和问答的预期值，入库复测结果另见 [ingestion-results.json](ingestion-results.json)。

| 资料 | 测试问题 | 期待的回答与证据 |
|---|---|---|
| [UW PDF](https://courses.cs.washington.edu/courses/cse332/25sp/lecture/11-hash2.pdf) | 按二次探测依次把 89、18、49、58、79 插入大小为 10 的空哈希表，哪些槽位有值？ | 第 25 页。0→49、2→58、3→79、8→18、9→89，其余为空。 |
| [UW PPTX](https://courses.cs.washington.edu/courses/cse332/25sp/lecture/11-hash2.pptx) | 原槽位被占后，二次探测的前四个偏移是多少？当表大小为素数且负载因子小于一半时，能保证什么？ | 第 24 张给出 1、4、9、16。第 26 或 27 张说明一定能找到空槽。 |
| [UTS Word 指南](https://educationexpress.uts.edu.au/collections/inclusive-accessible-practices/resources/microsoft-word-accessible-practice/) | Mac 版 Word 的样式窗格中，Normal 和 Heading 1 之间是什么？截图列出了哪些标题级别？ | Headings 章节。中间是 No Spacing，标题级别为 Heading 1、Heading 2、Heading 3。 |
| [上海理工大学教学大纲](https://oece.usst.edu.cn/2024/0402/c9007a317786/page.htm) | 「桥梁工程的基本知识」模块支持哪些课程目标？学生有哪两项学习任务？ | 「教学模块」表的桥梁示例行。支持目标 1、4、5。学生在蓝墨云班课平台观看桥梁视频，并撰写桥梁发展与创新报告。 |
| [UTS PowerPoint 指南](https://educationexpress.uts.edu.au/collections/inclusive-accessible-practices/resources/microsoft-powerpoint-accessible-practice/) | 打开 Check Accessibility 用哪个选项卡？表格列用交替底色的选项叫什么？ | 第 4 张的 Review 选项卡和第 17 张的 Banded Columns。 |
| [中科大 ClassIn PDF](https://www.teach.ustc.edu.cn/wp-content/uploads/2022/10/%E7%BA%BF%E4%B8%8A%E6%95%99%E5%AD%A6%E6%93%8D%E4%BD%9C%E8%AF%B4%E6%98%8E2022%E7%A7%8B-%E6%95%99%E5%B8%88%E7%80%9A%E6%B5%B7%E6%95%99%E5%AD%A6%E7%BD%91ClassIn.pdf) | 云盘支持哪些课件格式？「打开云盘课件内容上课」这页截图中，与试卷和授权有关的列表项叫什么？ | 第 8 页。格式为 EDB 板书、PPT、PDF、Word、图片、音频、视频和 TXT，截图里有「试卷资源」和「授权资源」。 |
