# 测试数据与 Fixture 规范

## 1. 目标

让测试可复现、可脱敏、可在 CI 中运行。禁止把真实私人 vault、客户资料、密钥或未授权文档提交到仓库。

## 2. Fixture 分类

建议目录：

    tests/
      fixtures/
        markdown/
          frontmatter/
          obsidian/
          commonmark/
          malformed/
          unicode/
        vaults/
          empty/
          minimal/
          obsidian_like/
          mixed_language/
          large_synthetic/
          exclude_allow/
        golden/
          queries.jsonl
          relevance.jsonl
          README.md
        transactions/
          journals/
          before_images/
          after_images/
          divergent/
        git/
          clean_repo/
          dirty_repo/
          no_git/
      benchmarks/
        generate_corpus.py
        run_index_benchmark.py
        run_search_benchmark.py

## 3. Fixture Manifest

每个复杂 fixture 附 manifest，至少记录：
- fixture_id、版本、用途；
- 文件数量、总字节数、Markdown 语法分布；
- 生成器版本和随机 seed；
- 预期文档数、块数、链接数；
- 隐私状态（synthetic/deidentified/approved）；
- 关联测试 ID。

## 4. Golden Set 结构

每条查询至少包含：
- query_id、query_text、query_type；
- vault_fixture_id；
- filters（state、visibility、path、tags 等）；
- relevant_blocks（block_id 或稳定 locator）；
- relevance_grade；
- must_not_return；
- 标注说明和标注版本。

Golden set 需包含中文短词、bigram、长词、英文、中英混合、下划线标识符、标题/正文/表格/代码块、排除区和 allow 白名单。

## 5. 大规模合成数据

10k benchmark 必须由脚本生成，固定 seed。生成器应可控制：
- 文件数、每文件长度、标题层级、Frontmatter 字段；
- 中文/英文比例、标识符密度、重复率；
- 表格、列表、代码块、wikilink 的比例；
- 高频词和长尾词分布。

报告中保存生成参数和运行环境，不保存真实库正文。

## 6. 事务 Fixture

事务测试必须覆盖：
- journal 不存在；
- staging 半写；
- journal 已落盘、尚未 apply；
- 部分文件已替换；
- 所有文件已替换、索引未更新；
- 目标文件被外部修改形成 divergent；
- 恢复过程中再次崩溃。

所有恢复测试验证文件 hash、journal 状态、索引 dirty 状态和是否存在残留 staging。
