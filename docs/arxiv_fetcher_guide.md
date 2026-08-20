# arXiv 论文爬取模块使用指南

## 📖 模块介绍

`arxiv_fetcher.py` 是负责从 arXiv 获取最新论文的核心模块。它提供了灵活的配置选项，可以按类别、关键词筛选论文，并自动保存结果。

## 🔧 主要功能

### 1. ArxivFetcher 类

主要的论文爬取类，提供以下功能：

- ✅ 按类别搜索论文
- ✅ 按关键词过滤论文
- ✅ 自定义结果数量
- ✅ 自动保存论文数据
- ✅ 生成统计报告

### 2. 关键方法

#### `fetch_papers(days_back=1)`
获取指定天数内的论文

```python
from src.crawler.arxiv_fetcher import ArxivFetcher

fetcher = ArxivFetcher(config)
papers = fetcher.fetch_papers(days_back=2)  # 获取过去2天的论文
```

#### `build_query()`
构建 arXiv 搜索查询字符串

```python
query = fetcher.build_query()
# 例如: "(cat:cs.AI OR cat:cs.LG) AND (ti:\"LLM\" OR abs:\"LLM\")"
```

#### `get_paper_stats(papers)`
获取论文统计信息

```python
stats = fetcher.get_paper_stats(papers)
# 返回: 总数、类别分布、作者统计等
```

#### `print_paper_summary(papers)`
打印论文摘要和统计信息

## ⚙️ 配置说明

在 `config/config.yaml` 中配置爬取参数：

```yaml
arxiv:
  # 研究领域类别
  categories:
    - "cs.AI"   # 人工智能
    - "cs.LG"   # 机器学习
  
  # 关键词过滤（可选）
  keywords:
    - "large language model"
    - "LLM"
    - "transformer"
  
  # 最大结果数量
  max_results: 20
  
  # 排序方式: submittedDate, relevance, lastUpdatedDate
  sort_by: "submittedDate"
  
  # 排序顺序: descending, ascending
  sort_order: "descending"
```

### 常用 arXiv 类别代码

**计算机科学 (cs.XX):**
- `cs.AI` - Artificial Intelligence (人工智能)
- `cs.LG` - Machine Learning (机器学习)
- `cs.CV` - Computer Vision (计算机视觉)
- `cs.CL` - Computation and Language (NLP)
- `cs.NE` - Neural and Evolutionary Computing
- `cs.RO` - Robotics (机器人)
- `cs.CR` - Cryptography and Security (密码学)

**统计学 (stat.XX):**
- `stat.ML` - Machine Learning (统计机器学习)

**更多类别**: https://arxiv.org/category_taxonomy

## 📊 数据格式

### 论文对象结构

```json
{
  "id": "2310.12345",
  "title": "论文标题",
  "authors": ["作者1", "作者2"],
  "abstract": "论文摘要...",
  "categories": ["cs.AI", "cs.LG"],
  "primary_category": "cs.AI",
  "published": "2024-10-13T00:00:00",
  "updated": "2024-10-13T00:00:00",
  "pdf_url": "https://arxiv.org/pdf/2310.12345",
  "entry_url": "https://arxiv.org/abs/2310.12345",
  "fetched_at": "2024-10-13T10:30:00"
}
```

### 保存的文件

- `data/papers/papers_YYYY-MM-DD.json` - 按日期保存的论文
- `data/papers/latest.json` - 最新的论文数据（包含元信息）

## 🚀 使用示例

### 示例 1: 基本使用

```python
from src.utils import load_config, load_env, setup_logging
from src.crawler.arxiv_fetcher import ArxivFetcher

# 加载配置
load_env()
config = load_config()
logger = setup_logging(config)

# 创建爬取器
fetcher = ArxivFetcher(config)

# 获取论文
papers = fetcher.fetch_papers(days_back=1)

# 打印摘要
if papers:
    fetcher.print_paper_summary(papers)
```

### 示例 2: 自定义配置

```python
# 临时修改配置
config['arxiv']['max_results'] = 10
config['arxiv']['categories'] = ['cs.CV']
config['arxiv']['keywords'] = ['diffusion', 'image generation']

fetcher = ArxivFetcher(config)
papers = fetcher.fetch_papers(days_back=7)
```

### 示例 3: 获取统计信息

```python
papers = fetcher.fetch_papers()
stats = fetcher.get_paper_stats(papers)

print(f"总论文数: {stats['total_papers']}")
print(f"类别分布: {stats['category_distribution']}")
print(f"高产作者: {stats['prolific_authors']}")
```

### 示例 4: 处理论文数据

```python
papers = fetcher.fetch_papers()

for paper in papers:
    print(f"标题: {paper['title']}")
    print(f"作者: {', '.join(paper['authors'])}")
    print(f"PDF: {paper['pdf_url']}")
    print(f"摘要: {paper['abstract'][:200]}...")
    print("-" * 60)
```

## 🧪 测试

运行测试脚本：

```bash
python test_fetcher.py
```

测试脚本会：
1. 测试查询构建功能
2. 测试论文获取功能
3. 测试数据保存和加载

## 📝 注意事项

1. **API 限制**: arXiv API 有速率限制，建议不要频繁请求
2. **日期过滤**: 默认只获取指定天数内的论文
3. **关键词匹配**: 关键词在标题和摘要中进行 OR 匹配
4. **类别组合**: 多个类别之间是 OR 关系
5. **数据存储**: 论文数据以 JSON 格式保存在 `data/papers/` 目录

## 🔍 常见问题

### Q: 为什么没有找到论文？
A: 检查以下几点：
- 确认类别代码正确
- 关键词可能过于严格，尝试减少或修改
- 检查日期范围是否合适
- 查看日志了解详细信息

### Q: 如何获取更多论文？
A: 修改 `config.yaml` 中的 `max_results` 值

### Q: 如何只按类别搜索，不限制关键词？
A: 在 `config.yaml` 中将 `keywords` 设为空列表：
```yaml
keywords: []
```

### Q: 论文数据保存在哪里？
A: 默认保存在 `data/papers/` 目录，可在 `config.yaml` 中修改

## 🔗 相关链接

- [arXiv API 文档](https://info.arxiv.org/help/api/index.html)
- [arXiv Python 库](https://github.com/lukasschwab/arxiv.py)
- [arXiv 类别列表](https://arxiv.org/category_taxonomy)
