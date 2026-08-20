"""
Daily arXiv Agent 演示脚本

快速体验：抓取、总结、分析 arXiv 论文
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils import load_config, load_env, setup_logging, load_json, pick_text


def demo_quick():
    """快速演示：展示已有的论文数据"""
    load_env()
    config = load_config()
    logger = setup_logging(config)
    text = lambda zh, en: pick_text(config, zh, en)

    print("\n" + "=" * 60)
    print(text("📚 Daily arXiv 演示", "📚 Daily arXiv Demo"))
    print("=" * 60)

    papers_data = load_json("data/papers/latest.json")
    if papers_data and papers_data.get("papers"):
        papers = papers_data["papers"]
        print(text(f"\n✅ 找到 {len(papers)} 篇论文", f"\n✅ Found {len(papers)} papers"))
        for i, p in enumerate(papers[:5], 1):
            print(f"  [{i}] {p.get('title', 'N/A')[:80]}")
    else:
        print(text("\n⚠️  暂无论文数据，请先运行: python main.py", "\n⚠️  No paper data. Run: python main.py"))

    summaries_data = load_json("data/summaries/latest.json")
    if summaries_data:
        print(text("\n✅ 论文总结数据可用", "\n✅ Paper summaries available"))

    analysis_data = load_json("data/analysis/latest.json")
    if analysis_data:
        print(text("\n✅ 趋势分析数据可用", "\n✅ Trend analysis available"))

    print("\n" + "=" * 60)
    print(text("提示: 运行 'python main.py' 执行完整流程", "Tip: Run 'python main.py' for full pipeline"))
    print(text("提示: 查看 data/ 目录下的报告和分析结果", "Tip: Check reports and analysis in data/ directory"))
    print("=" * 60 + "\n")


if __name__ == "__main__":
    demo_quick()
