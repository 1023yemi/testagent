# 航运智能账单助手 Agent

一个基于 Python 与 LangChain 的航运账单处理流水线。它支持 EML、PDF、图片、Excel、DOC/DOCX 以及已有账单 JSON，输出每笔费用一条的标准 JSON 记录。

## 特性

- EML 正文、邮件头及附件的递归解析；
- PDF 文本提取，图片/PDF 可接入指定 OCR API；
- Excel、Word 表格解析；
- LangChain 结构化抽取（未配置模型时自动使用可审计的规则回退）；
- 费用名称、币种、付款方式标准化；
- 金额、币种、合计、OCR 易错字符和重复费用校验；
- 分层匹配已有账单并决策 `CREATE`、`UPDATE`、`NO_CHANGE`、`PENDING_REVIEW`；
- 输出字段证据与处理依据，便于财务审计和人工复核。

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

如需使用大模型抽取，设置环境变量 `OPENAI_API_KEY`（以及可选的 `OPENAI_MODEL`）。未设置时项目仍可运行，但将使用规则抽取器。

## 运行

```bash
python -m app.main \
  --input "data/深圳容宇 PRE-ALERT SSZSE26093128 VASINGER LLC 1x40HQ  CNTR NO._ TIIU8975975   MBL NO._ OOLU4055331281  Arrived time 2026-10-30.eml" \
  --existing-bills samples/existing_bills.json \
  --accounting-entity "Origin Agent" \
  --output output/result.json
```

对于扫描 PDF 或图片，指定 OCR 可访问的下载地址：

```bash
python -m app.main --input data/图片示例.png --public-url https://example.com/bill.png
```

对于 EML 内的扫描附件，使用文件名到 OCR URL 的映射：

```bash
python -m app.main --input data/mail.eml --ocr-url-map samples/ocr_url_map.example.json --accounting-entity "Origin Agent"
```

OCR API 默认使用题目指定接口 `http://36.103.199.11:5002/process`。可通过 `OCR_API_URL` 环境变量覆盖。程序不会把本地文件路径发送给 OCR 服务；只有提供 `--public-url` 时才会调用该服务。

`.doc` 会优先使用本机 LibreOffice（`soffice`）转换为 DOCX，以保留表格；没有 LibreOffice 时使用 Antiword 或 OLE 文本回退。`.docx`、`.xls`、`.xlsx` 无需 Office。

## 输出约定

- 每个费用项目输出一条记录；无法提取的值为 `null`；
- 更新仅包含有明确来源的新值，其他字段继承原账单；
- 校验失败、匹配歧义或关键字段低置信度时输出 `PENDING_REVIEW`；
- `audit_trail` 保留来源、原始字段、校验和匹配依据。

## 测试

```bash
python -m pytest -q
```

设计原则及 Harness 方案见 [docs/design.md](docs/design.md)。

## 项目优化建议

1. 完善 OCR 异常处理，增加超时重试和结果缓存，提高识别稳定性。
2. 扩充费用别名、币种和付款方式规则，减少不同账单写法带来的误差。
3. 设置字段置信度阈值，将低置信度或冲突结果转交人工复核。
4. 加强账单匹配与去重，避免同名费用误匹配和重复导入。
5. 完善 AR/AP 判断，结合记账主体、交易双方和实际收付款方向。
6. 保存完整原始文本、字段来源和修改记录，方便审计与问题追踪。
7. 扩充真实样例回归测试，覆盖各类文件、金额数值类型及新增和更新场景。
