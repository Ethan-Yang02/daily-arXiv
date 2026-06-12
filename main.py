"""
Daily arXiv Agent - 主程序入口 / Main entry

每日追踪 arXiv 最新论文，使用 LLM 进行总结和分析 /
Track latest arXiv papers daily and summarize/analyze them with LLMs
"""
import sys
import json
from pathlib import Path
from datetime import datetime

from src.utils_1.push_dedupe import filter_unseen_papers, mark_papers_as_seen

# 添加项目根目录到 Python 路径 / Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils import load_config, load_env, setup_logging, get_date_string, pick_text


def write_run_status(status, message="", **kwargs):
    """写入本次运行状态，供 scheduler 判断是否应该发送空日报。"""
    path = Path("data/run_status/latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "date": get_date_string(),
        "status": status,
        "message": message,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    payload.update(kwargs)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def main():
    """主函数 / Main function"""
    load_env()
    config = load_config()
    logger = setup_logging(config)
    text = lambda zh, en: pick_text(config, zh, en)

    write_run_status(
        "running",
        "任务正在执行",
        fetched_count=0,
        skipped_seen_count=0,
        skipped_duplicate_count=0,
        new_papers_count=0,
        filtered_papers_count=0,
        final_papers_count=0,
        fetch_mode="unknown",
    )

    logger.info("=" * 60)
    logger.info(text("Daily arXiv Agent 启动", "Daily arXiv Agent started"))
    logger.info(f"{text('日期', 'Date')}: {get_date_string()}")
    logger.info("=" * 60)

    fetched_count = 0
    skipped_seen_count = 0
    skipped_duplicate_count = 0
    unseen_count = 0
    filtered_count = 0
    final_count = 0
    fetch_mode = "fixed"
    fetch_stats = {}

    try:
        logger.info(text("步骤 1: 爬取 arXiv 论文...", "Step 1: Fetching arXiv papers..."))
        from src.crawler.arxiv_fetcher import ArxivFetcher
        fetcher = ArxivFetcher(config)

        dedupe_config = config.get("dedupe", {})
        dedupe_enabled = dedupe_config.get("enabled", True)
        state_path = dedupe_config.get("state_path", "data/state/papers_state.json")
        keep_days = int(dedupe_config.get("keep_days", 180))

        adaptive_config = config.get("adaptive_fetch", {})
        adaptive_enabled = bool(adaptive_config.get("enabled", False)) and dedupe_enabled

        if adaptive_enabled:
            fetch_mode = "adaptive"
            backfill_days = int(adaptive_config.get("backfill_days", 14))
            papers = fetcher.fetch_papers_adaptive(
                state_path=state_path,
                days_back=backfill_days,
            )
            fetch_stats = getattr(fetcher, "last_fetch_stats", {}) or {}

            fetched_count = int(fetch_stats.get("scanned_count", len(papers or [])) or 0)
            skipped_seen_count = int(fetch_stats.get("skipped_seen_count", 0) or 0)
            skipped_duplicate_count = int(fetch_stats.get("skipped_duplicate_count", 0) or 0)
            unseen_count = len(papers or [])

            logger.info(text(
                f"自适应抓取统计：扫描 {fetched_count} 篇，已爬过 {skipped_seen_count} 篇，重复 {skipped_duplicate_count} 篇，新论文 {unseen_count} 篇",
                f"Adaptive fetch stats: scanned {fetched_count}, skipped seen {skipped_seen_count}, duplicate {skipped_duplicate_count}, unseen {unseen_count}"
            ))

            # adaptive fetch 已经在抓取层过滤 seen；这里只负责把本次新论文标记为 seen。
            if papers:
                marked_count = mark_papers_as_seen(
                    papers,
                    state_path=state_path,
                    keep_days=keep_days,
                )
                logger.info(text(
                    f"已将 {marked_count} 篇新论文标记为已爬取",
                    f"Marked {marked_count} new papers as seen"
                ))

        else:
            fetch_mode = "fixed"
            papers = fetcher.fetch_papers(days_back=2)
            fetch_stats = getattr(fetcher, "last_fetch_stats", {}) or {}
            fetched_count = len(papers or [])

            if papers and dedupe_enabled:
                unseen_papers, skipped_seen_papers = filter_unseen_papers(papers, state_path)
                skipped_seen_count = len(skipped_seen_papers)
                unseen_count = len(unseen_papers)

                logger.info(text(
                    f"爬取去重完成：抓到 {fetched_count} 篇，已爬过 {skipped_seen_count} 篇，新论文 {unseen_count} 篇",
                    f"Fetch dedupe done: {fetched_count} fetched, {skipped_seen_count} already seen, {unseen_count} new"
                ))

                if unseen_papers:
                    marked_count = mark_papers_as_seen(
                        unseen_papers,
                        state_path=state_path,
                        keep_days=keep_days,
                    )
                    logger.info(text(
                        f"已将 {marked_count} 篇新论文标记为已爬取",
                        f"Marked {marked_count} new papers as seen"
                    ))

                papers = unseen_papers
            else:
                unseen_count = len(papers or [])

        if not papers:
            logger.info(text(
                "本次没有新的未爬取论文，保存空结果并结束任务",
                "No new unseen papers this run, saving empty result and stopping"
            ))

            try:
                fetcher._save_papers([])
            except Exception as e:
                logger.warning(text(
                    f"保存空论文列表失败: {e}",
                    f"Failed to save empty paper list: {e}"
                ))

            if fetched_count == 0:
                status = "no_matching_papers"
                message = "今天没有从 arXiv 抓到符合条件的论文，因此本次推送论文数量为 0。"
            else:
                status = "no_new_papers"
                message = "本次扫描到的候选论文全部是之前已经爬取过的论文，因此本次推送论文数量为 0。"

            write_run_status(
                status,
                message,
                fetched_count=fetched_count,
                skipped_seen_count=skipped_seen_count,
                skipped_duplicate_count=skipped_duplicate_count,
                new_papers_count=0,
                filtered_papers_count=0,
                final_papers_count=0,
                fetch_mode=fetch_mode,
                fetch_stats=fetch_stats,
            )
            return

        fetcher.print_paper_summary(papers)

        # LLM 智能过滤 / LLM-based relevance filtering
        if config.get("llm_filter", {}).get("enabled", False):
            logger.info(text("\n步骤 1.5: 使用 LLM 智能过滤论文...", "\nStep 1.5: Filtering papers with LLM..."))

            from src.filter.llm_paper_filter import LLMPaperFilter

            llm_filter = LLMPaperFilter(config)
            filtered_papers = llm_filter.filter_papers(papers)
            filtered_count = len(filtered_papers or [])

            if not filtered_papers:
                logger.warning(text(
                    "⚠️ LLM 过滤后没有保留论文，本次任务结束",
                    "⚠️ No papers retained after LLM filtering, stopping this run"
                ))

                try:
                    fetcher._save_papers([])
                except Exception as e:
                    logger.warning(text(
                        f"保存空论文列表失败: {e}",
                        f"Failed to save empty paper list: {e}"
                    ))

                write_run_status(
                    "no_selected_papers",
                    "今天有新论文，但 LLM 筛选后没有符合关注方向的论文，因此本次推送论文数量为 0。",
                    fetched_count=fetched_count,
                    skipped_seen_count=skipped_seen_count,
                    skipped_duplicate_count=skipped_duplicate_count,
                    new_papers_count=unseen_count,
                    filtered_papers_count=0,
                    final_papers_count=0,
                    fetch_mode=fetch_mode,
                    fetch_stats=fetch_stats,
                )
                return

            papers = filtered_papers
            fetcher._save_papers(papers)

            logger.info(text(
                f"✅ LLM 过滤后保留 {len(papers)} 篇论文",
                f"✅ {len(papers)} papers retained after LLM filtering"
            ))
        else:
            filtered_count = len(papers)
            fetcher._save_papers(papers)

        final_count = len(papers)

        # 第三步 - 实现论文总结 ✅ / Step 3 - Summarize papers
        logger.info(text("\n步骤 2: 总结论文...", "\nStep 2: Summarizing papers..."))
        from src.summarizer.paper_summarizer import PaperSummarizer

        try:
            summarizer = PaperSummarizer(config)
            summarized_papers = summarizer.summarize_papers(papers)

            logger.info(text("\n生成每日报告...", "\nGenerating daily report..."))
            report = summarizer.generate_daily_report(summarized_papers)

            report_path = f"data/summaries/report_{get_date_string()}.md"
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(text(f"📄 每日报告已保存到: {report_path}", f"📄 Daily report saved to: {report_path}"))

        except Exception as e:
            logger.error(text(f"论文总结失败: {str(e)}", f"Paper summarization failed: {str(e)}"))
            logger.info(text("继续执行后续步骤...", "Continuing with following steps..."))
            summarized_papers = papers

        # 第四步 - 实现趋势分析 ✅ / Step 4 - Analyze trends
        logger.info(text("\n步骤 3: 分析研究趋势...", "\nStep 3: Analyzing research trends..."))
        try:
            from src.analyzer.trend_analyzer import TrendAnalyzer
            from src.summarizer.llm_factory import LLMClientFactory

            llm_client = LLMClientFactory.create_client(config)

            from src.utils import load_json
            summaries_data = load_json("data/summaries/latest.json")
            if isinstance(summaries_data, dict):
                summaries = summaries_data.get("summaries") or summaries_data.get("papers") or []
            elif isinstance(summaries_data, list):
                summaries = summaries_data
            else:
                summaries = []

            analyzer = TrendAnalyzer(config, llm_client)
            analysis = analyzer.analyze(papers, summaries)

            if analysis:
                analyzer.print_analysis_summary(analysis)

        except Exception as e:
            logger.error(text(f"趋势分析失败: {str(e)}", f"Trend analysis failed: {str(e)}"), exc_info=True)
            logger.info(text("继续执行后续步骤...", "Continuing with following steps..."))

        write_run_status(
            "success",
            f"本次任务成功完成，最终准备推送 {final_count} 篇论文。",
            fetched_count=fetched_count,
            skipped_seen_count=skipped_seen_count,
            skipped_duplicate_count=skipped_duplicate_count,
            new_papers_count=unseen_count,
            filtered_papers_count=filtered_count,
            final_papers_count=final_count,
            fetch_mode=fetch_mode,
            fetch_stats=fetch_stats,
        )

        logger.info("=" * 60)
        logger.info(text("✅ 所有任务完成！", "✅ All tasks completed!"))
        logger.info("=" * 60)
        logger.info(text("提示: 运行完成后请查看邮件日报和 data 目录中的结果", "Tip: check email digest and generated files under data/"))

    except Exception as e:
        write_run_status(
            "failed",
            f"任务执行失败: {str(e)}",
            fetched_count=fetched_count,
            skipped_seen_count=skipped_seen_count,
            skipped_duplicate_count=skipped_duplicate_count,
            new_papers_count=unseen_count,
            filtered_papers_count=filtered_count,
            final_papers_count=final_count,
            fetch_mode=fetch_mode,
            fetch_stats=fetch_stats,
            error=str(e),
        )
        logger.error(text(f"❌ 执行出错: {str(e)}", f"❌ Execution failed: {str(e)}"), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
