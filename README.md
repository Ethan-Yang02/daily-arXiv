# Daily arXiv Digest：每日 arXiv 智能论文邮件推送

Daily arXiv Digest 是一个面向研究人员的每日论文自动化工具。它会定时从 arXiv 抓取指定领域的最新论文，先做去重，再用 LLM 判断论文是否与你的研究方向相关，最后生成中文邮件日报。邮件中包含今日概览、词云、类别分布、高频词、研究热点、技术趋势、未来方向、创新想法和重点论文卡片。

本版本以“邮件日报”为核心，不依赖 Web 服务或 systemd 部署脚本。仓库中只保留了当前运行所需的核心代码和 `scripts` 下的三个常用命令。

## 功能特性

- **arXiv 最新论文抓取**：支持多个 arXiv category，例如 `cs.LG`、`cs.AI`、`cs.CV`、`cs.CL`、`stat.ML`。
- **自适应分页抓取**：当最新窗口内重复论文较多时，会继续向更旧页面翻页，直到找到足够数量的未爬取论文，或达到扫描上限。
- **双层去重**：
  - `seen`：只要爬取过，就不会再次进入 LLM 过滤，节省调用成本。
  - `pushed`：只有邮件发送成功后才标记，避免重复推送。
- **LLM 智能过滤**：用自然语言描述你的研究兴趣，自动筛选相关论文。
- **论文总结与趋势分析**：生成论文摘要、研究热点、技术趋势、未来方向和创新想法。
- **HTML 邮件日报**：邮件直接展示核心研究情报；如果当天没有新论文，会发送“今日新论文 0 篇”的空日报，而不是重复推送旧内容。
- **简单脚本管理**：使用 `scripts/start.sh`、`scripts/state.sh`、`scripts/kill.sh` 启动、查看和停止调度器。

## 目录结构

```text
.
├── config/config.yaml              # 主配置文件
├── main.py                         # 单次运行入口：抓取、过滤、总结、分析
├── scheduler.py                    # 定时调度入口：每日运行并发送邮件
├── scripts/
│   ├── start.sh                    # 后台启动调度器
│   ├── state.sh                    # 查看调度器状态
│   └── kill.sh                     # 停止调度器
├── src/
│   ├── crawler/arxiv_fetcher.py    # arXiv 抓取与自适应分页
│   ├── filter/llm_paper_filter.py  # LLM 相关性过滤
│   ├── summarizer/                 # LLM 客户端与论文总结
│   ├── analyzer/trend_analyzer.py  # 词云、统计与趋势分析
│   ├── notifier/email_notifier.py  # HTML 邮件日报
│   └── utils_1/push_dedupe.py      # seen/pushed 去重状态
├── requirements.txt
└── .env.example
```

运行过程中会自动生成：

```text
data/      # 论文、摘要、分析、去重状态
logs/      # 运行日志
.env       # 本地密钥文件，需要你自己创建，默认不会提交
```

## 1. 安装环境

推荐使用 Python 3.10 或 3.11。Python 3.12 通常也可以，但部分科学计算包在不同平台上可能需要更长安装时间。

### 方式 A：conda

```bash
conda create -n daily-arxiv python=3.10 -y
conda activate daily-arxiv
pip install -r requirements.txt
```

### 方式 B：venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 2. 配置密钥

复制环境变量模板：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```bash
vim .env
```

根据你使用的 LLM provider 填写对应密钥。例如使用 DeepSeek：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
EMAIL_PASSWORD=your_email_app_password_here
```

注意：`EMAIL_PASSWORD` 一般是邮箱的“客户端授权码 / 应用专用密码”，不是网页登录密码。请不要把 `.env` 提交到公开仓库。

## 3. 修改主配置

编辑：

```bash
vim config/config.yaml
```

### 3.1 arXiv 分类

```yaml
arxiv:
  categories:
    - "cs.LG"
    - "cs.AI"
    - "cs.CV"
    - "cs.CL"
    - "stat.ML"
  keywords: []
  sort_by: "submittedDate"
  sort_order: "descending"
```

`keywords: []` 表示不做关键词硬过滤，交给 LLM 智能判断。这样召回更宽，不容易漏掉相关论文。

### 3.2 自适应抓取

```yaml
adaptive_fetch:
  enabled: true
  min_unseen_papers: 50
  page_size: 100
  max_scan_results: 500
  backfill_days: 14
  delay_seconds: 15
  num_retries: 1
```

含义：

- `min_unseen_papers`：希望每天至少收集多少篇未爬取候选论文，再送入 LLM 过滤。
- `page_size`：每次向 arXiv 请求一页多少篇，建议不超过 100。
- `max_scan_results`：单次任务最多扫描多少篇，防止请求过多。
- `backfill_days`：最多回看多少天内的论文。
- `delay_seconds`：arXiv 请求间隔。共享服务器建议设大一点，避免触发限流。

### 3.3 LLM 过滤

```yaml
llm_filter:
  enabled: true
  threshold: 0.65
  max_selected: 20
  fail_open: true
  topic: |
    我关注模型压缩、模型加速、高效多模态大模型、高效长上下文、推理加速、训练加速相关论文。
```

`max_selected` 决定 LLM 最多保留多少篇论文。邮件默认展示全部 LLM 过滤后的论文。

### 3.4 LLM provider

```yaml
llm:
  provider: "deepseek"
  deepseek:
    model: "deepseek-chat"
    base_url: "https://api.deepseek.com"
```

可选 provider：

```text
openai, gemini, claude, deepseek, vllm
```

API Key 推荐写在 `.env`，不要直接写进 `config/config.yaml`。

### 3.5 邮件配置

Gmail 示例：

```yaml
scheduler:
  notification:
    enabled: true
    email:
      smtp_server: "smtp.gmail.com"
      smtp_port: 587
      sender: "your-email@gmail.com"
      password: ""
      recipients:
        - "recipient@example.com"
      on_success: true
      on_failure: true
```

163 邮箱示例：

```yaml
scheduler:
  notification:
    enabled: true
    email:
      smtp_server: "smtp.163.com"
      smtp_port: 465
      sender: "your-email@163.com"
      password: ""
      recipients:
        - "recipient@example.com"
      on_success: true
      on_failure: true
```

QQ 邮箱示例：

```yaml
scheduler:
  notification:
    enabled: true
    email:
      smtp_server: "smtp.qq.com"
      smtp_port: 587
      sender: "your-email@qq.com"
      password: ""
      recipients:
        - "recipient@example.com"
      on_success: true
      on_failure: true
```

真正的邮箱授权码请写入 `.env`：

```env
EMAIL_PASSWORD=your_email_app_password_here
```

## 4. 测试邮件

先只测试邮件能否发送：

```bash
python - <<'PY'
from src.utils import load_config, load_env
from src.notifier.email_notifier import send_test_email

load_env()
config = load_config()
email_config = config["scheduler"]["notification"]["email"]
email_config["_language"] = config.get("app", {}).get("language", "zh")
send_test_email(email_config)
PY
```

如果收到测试邮件，说明 SMTP 配置可用。

## 5. 单次运行

建议先手动跑一次完整流程：

```bash
python main.py
```

该命令会执行：

```text
arXiv 抓取 → seen 去重 → LLM 过滤 → 论文总结 → 趋势分析
```

但它不会自动发送日报邮件。邮件发送由 `scheduler.py` 负责。

## 6. 定时运行并发送邮件

### 前台调试

```bash
python scheduler.py
```

如果 `scheduler.run_on_start: true`，启动后会立即执行一次；如果是 `false`，则等待每天 `run_time` 执行。

`scheduler.misfire_grace_time` 表示定时任务允许延迟启动的秒数，默认值为 `300`。这可以避免系统短暂繁忙或调度线程晚到一两秒时，整天的任务被直接跳过。

### 后台启动

```bash
bash scripts/start.sh
```

查看状态：

```bash
bash scripts/state.sh
```

查看日志：

```bash
tail -f logs/scheduler.log
```

停止：

```bash
bash scripts/kill.sh
```

## 7. 去重机制说明

去重状态保存在：

```text
data/state/papers_state.json
```

结构大致为：

```json
{
  "seen": {
    "2506.12345": {
      "seen_at": "2026-06-12T09:00:00",
      "title": "..."
    }
  },
  "pushed": {
    "2506.12345": {
      "pushed_at": "2026-06-12T09:05:00",
      "title": "..."
    }
  }
}
```

- `seen`：只要论文被抓取到，就记录。以后不会再进入 LLM 过滤。
- `pushed`：只有邮件发送成功后才记录。以后不会重复推送。

如果某天没有新论文，系统会发送“今日新论文推送数量为 0”的邮件，而不是重复推送上一次的内容。

## 8. 常见问题

### 8.1 arXiv 返回 429 / 503

这通常是请求过于频繁或共享出口 IP 被限流。建议：

```yaml
adaptive_fetch:
  delay_seconds: 15
  num_retries: 1
  max_scan_results: 500
```

不要连续手动重复运行 `python scheduler.py`。

### 8.2 邮件认证失败

请确认：

- 使用的是邮箱授权码，不是网页登录密码。
- `sender` 与授权码所属邮箱一致。
- `.env` 中存在 `EMAIL_PASSWORD`。
- 465/994 端口使用 SSL，587 端口使用 STARTTLS；本工具已自动兼容。

### 8.3 LLM 没筛出论文

可以降低阈值或放宽 topic：

```yaml
llm_filter:
  threshold: 0.55
  max_selected: 30
```

### 8.4 邮件展示论文数量不够

邮件默认展示全部 LLM 过滤后的论文。如果想限制数量：

```yaml
email_digest:
  max_papers: 20
```

如果想全部展示：

```yaml
email_digest:
  max_papers: "all"
```

## 9. 开源前注意

请确认以下文件不会提交到公开仓库：

```text
.env
data/
logs/
```

本仓库默认 `.gitignore` 已排除这些文件。

## 10. License

见 `LICENSE`。


## 11. 致谢

本仓库基于开源仓库https://github.com/gejifeng/daily-arxiv 上改进。
