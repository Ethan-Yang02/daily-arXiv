"""
arXiv 论文爬取器

使用 arxiv API 获取指定领域的最新论文。
支持 adaptive fetch：当最新窗口内重复论文过多时，自动向更旧页面翻页，直到收集到足够数量的未爬取论文或达到扫描上限。
"""
import arxiv
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path

from src.utils import save_json, get_date_string, get_data_path, get_language, pick_text


class ArxivFetcher:
    """arXiv 论文爬取器"""

    def __init__(self, config: Dict[str, Any]):
        """初始化 / Initialize

        Args:
            config: 配置字典 / Config dictionary
        """
        self.config = config
        self.language = get_language(config)
        self.text = lambda zh, en: pick_text(self.config, zh, en)
        self.arxiv_config = config.get("arxiv", {})
        self.adaptive_config = config.get("adaptive_fetch", {})
        self.logger = logging.getLogger("daily_arxiv.fetcher")

        # 获取配置 / Read configuration
        self.categories = self.arxiv_config.get("categories", ["cs.AI"])
        self.keywords = self.arxiv_config.get("keywords", [])
        self.max_results = int(self.arxiv_config.get("max_results", 20))
        self.sort_by = self.arxiv_config.get("sort_by", "submittedDate")
        self.sort_order = self.arxiv_config.get("sort_order", "descending")

        # 保存最近一次抓取统计，供 main.py 写 run_status 使用
        self.last_fetch_stats = {}

    def build_query(self) -> str:
        """构建搜索查询 / Build search query"""
        if len(self.categories) == 1:
            category_query = f"cat:{self.categories[0]}"
        else:
            category_parts = [f"cat:{cat}" for cat in self.categories]
            category_query = "(" + " OR ".join(category_parts) + ")"

        if self.keywords:
            keyword_parts = []
            for keyword in self.keywords:
                keyword_parts.append(f'(ti:"{keyword}" OR abs:"{keyword}")')
            keyword_query = "(" + " OR ".join(keyword_parts) + ")"
            query = f"{category_query} AND {keyword_query}"
        else:
            query = category_query

        self.logger.info(self.text(f"构建的查询: {query}", f"Built query: {query}"))
        return query

    def _get_sort_options(self):
        """解析 arxiv.py 的排序参数"""
        sort_by_map = {
            "submittedDate": arxiv.SortCriterion.SubmittedDate,
            "relevance": arxiv.SortCriterion.Relevance,
            "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        }
        sort_criterion = sort_by_map.get(self.sort_by, arxiv.SortCriterion.SubmittedDate)

        sort_order_map = {
            "descending": arxiv.SortOrder.Descending,
            "ascending": arxiv.SortOrder.Ascending,
        }
        sort_order = sort_order_map.get(self.sort_order, arxiv.SortOrder.Descending)
        return sort_criterion, sort_order

    def fetch_papers(self, days_back: int = 1) -> List[Dict[str, Any]]:
        """普通固定窗口抓取。保留原行为：最多抓 arxiv.max_results 篇。"""
        self.logger.info("=" * 60)
        self.logger.info(self.text("开始爬取 arXiv 论文", "Starting arXiv paper fetching"))
        self.logger.info(self.text(f"类别: {', '.join(self.categories)}", f"Categories: {', '.join(self.categories)}"))
        if self.keywords:
            self.logger.info(self.text(f"关键词: {', '.join(self.keywords)}", f"Keywords: {', '.join(self.keywords)}"))
        self.logger.info(self.text(f"最大结果数: {self.max_results}", f"Max results: {self.max_results}"))
        self.logger.info("=" * 60)

        query = self.build_query()
        sort_criterion, sort_order = self._get_sort_options()

        search = arxiv.Search(
            query=query,
            max_results=self.max_results,
            sort_by=sort_criterion,
            sort_order=sort_order,
        )

        client = arxiv.Client(
            page_size=min(int(self.max_results), 100),
            delay_seconds=int(self.arxiv_config.get("delay_seconds", 15)),
            num_retries=int(self.arxiv_config.get("num_retries", 2)),
        )

        papers = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        try:
            self.logger.info(self.text("正在获取论文...", "Fetching papers..."))
            for result in client.results(search):
                if result.published.replace(tzinfo=None) < cutoff_date:
                    # submittedDate descending 时，后面的论文只会更旧，可以停止。
                    if self.sort_by == "submittedDate" and self.sort_order == "descending":
                        break
                    continue

                paper = self._extract_paper_info(result)
                papers.append(paper)
                self.logger.info(f"✓ [{len(papers)}] {paper['title'][:60]}...")

            self.last_fetch_stats = {
                "mode": "fixed",
                "scanned_count": len(papers),
                "within_window_count": len(papers),
                "unseen_count": len(papers),
                "skipped_seen_count": 0,
                "skipped_duplicate_count": 0,
                "target_unseen_count": len(papers),
                "max_scan_results": self.max_results,
                "days_back": days_back,
            }

            self.logger.info("=" * 60)
            self.logger.info(self.text(f"✅ 成功获取 {len(papers)} 篇论文", f"✅ Successfully fetched {len(papers)} papers"))
            self.logger.info("=" * 60)

            self._save_papers(papers)
            return papers

        except Exception as e:
            self.logger.error(self.text(f"❌ 获取论文失败: {str(e)}", f"❌ Failed to fetch papers: {str(e)}"), exc_info=True)
            raise

    def fetch_papers_adaptive(self, state_path: str, days_back: int = None) -> List[Dict[str, Any]]:
        """
        自适应分页抓取：
        - 从最新论文开始扫描；
        - 每扫到一篇就根据 seen 状态判断是否新论文；
        - 新论文数量达到 adaptive_fetch.min_unseen_papers 后停止；
        - 或扫描达到 adaptive_fetch.max_scan_results 后停止。

        注意：这里只过滤 seen，不写入 seen；写入 seen 仍由 main.py 在 LLM 之前统一处理。
        """
        from src.utils_1.push_dedupe import load_state, get_paper_id

        adaptive = self.adaptive_config or {}
        min_unseen_papers = int(adaptive.get("min_unseen_papers", 30))
        page_size = int(adaptive.get("page_size", min(self.max_results, 100)))
        max_scan_results = int(adaptive.get("max_scan_results", max(self.max_results, page_size)))
        backfill_days = int(adaptive.get("backfill_days", 14))
        delay_seconds = int(adaptive.get("delay_seconds", 15))
        num_retries = int(adaptive.get("num_retries", 1))

        if days_back is None:
            days_back = backfill_days

        page_size = max(1, min(page_size, 100))
        max_scan_results = max(page_size, max_scan_results)
        min_unseen_papers = max(1, min_unseen_papers)

        self.logger.info("=" * 60)
        self.logger.info(self.text("开始自适应爬取 arXiv 论文", "Starting adaptive arXiv paper fetching"))
        self.logger.info(self.text(f"类别: {', '.join(self.categories)}", f"Categories: {', '.join(self.categories)}"))
        if self.keywords:
            self.logger.info(self.text(f"关键词: {', '.join(self.keywords)}", f"Keywords: {', '.join(self.keywords)}"))
        self.logger.info(self.text(
            f"目标新论文数: {min_unseen_papers}, 每页: {page_size}, 最大扫描: {max_scan_results}, 回溯天数: {days_back}",
            f"Target unseen: {min_unseen_papers}, page size: {page_size}, max scan: {max_scan_results}, days back: {days_back}"
        ))
        self.logger.info("=" * 60)

        query = self.build_query()
        sort_criterion, sort_order = self._get_sort_options()

        search = arxiv.Search(
            query=query,
            max_results=max_scan_results,
            sort_by=sort_criterion,
            sort_order=sort_order,
        )

        client = arxiv.Client(
            page_size=page_size,
            delay_seconds=delay_seconds,
            num_retries=num_retries,
        )

        state = load_state(state_path)
        seen = state.get("seen", {}) if isinstance(state, dict) else {}
        seen_ids = set(seen.keys()) if isinstance(seen, dict) else set()
        selected_ids = set()

        cutoff_date = datetime.now() - timedelta(days=days_back)
        unseen_papers = []
        scanned_count = 0
        within_window_count = 0
        skipped_seen_count = 0
        skipped_duplicate_count = 0
        stopped_reason = "max_scan_results"

        try:
            self.logger.info(self.text("正在分页获取论文...", "Fetching papers with pagination..."))

            for result in client.results(search):
                scanned_count += 1

                published_naive = result.published.replace(tzinfo=None)
                if published_naive < cutoff_date:
                    if self.sort_by == "submittedDate" and self.sort_order == "descending":
                        stopped_reason = "older_than_cutoff"
                        self.logger.info(self.text(
                            f"遇到早于截止日期的论文，停止扫描: {result.published}",
                            f"Reached paper older than cutoff, stopping scan: {result.published}"
                        ))
                        break
                    continue

                within_window_count += 1
                paper = self._extract_paper_info(result)
                paper_id = get_paper_id(paper)

                if paper_id and paper_id in selected_ids:
                    skipped_duplicate_count += 1
                    continue

                if paper_id and paper_id in seen_ids:
                    skipped_seen_count += 1
                    if scanned_count % page_size == 0:
                        self.logger.info(self.text(
                            f"扫描 {scanned_count} 篇，已找到新论文 {len(unseen_papers)} 篇，已爬过 {skipped_seen_count} 篇",
                            f"Scanned {scanned_count}, found {len(unseen_papers)} unseen, skipped {skipped_seen_count} seen"
                        ))
                    continue

                if paper_id:
                    selected_ids.add(paper_id)

                unseen_papers.append(paper)
                self.logger.info(self.text(
                    f"✓ 新论文 [{len(unseen_papers)}/{min_unseen_papers}] scan={scanned_count}: {paper['title'][:70]}...",
                    f"✓ New paper [{len(unseen_papers)}/{min_unseen_papers}] scan={scanned_count}: {paper['title'][:70]}..."
                ))

                if len(unseen_papers) >= min_unseen_papers:
                    stopped_reason = "target_reached"
                    break

            self.last_fetch_stats = {
                "mode": "adaptive",
                "scanned_count": scanned_count,
                "within_window_count": within_window_count,
                "unseen_count": len(unseen_papers),
                "skipped_seen_count": skipped_seen_count,
                "skipped_duplicate_count": skipped_duplicate_count,
                "target_unseen_count": min_unseen_papers,
                "page_size": page_size,
                "max_scan_results": max_scan_results,
                "days_back": days_back,
                "stopped_reason": stopped_reason,
            }

            self.logger.info("=" * 60)
            self.logger.info(self.text(
                f"✅ 自适应爬取完成：扫描 {scanned_count} 篇，窗口内 {within_window_count} 篇，跳过已爬过 {skipped_seen_count} 篇，新论文 {len(unseen_papers)} 篇，停止原因: {stopped_reason}",
                f"✅ Adaptive fetch done: scanned {scanned_count}, within window {within_window_count}, skipped seen {skipped_seen_count}, unseen {len(unseen_papers)}, reason: {stopped_reason}"
            ))
            self.logger.info("=" * 60)

            # 保存当前新论文候选，避免 latest 继续保留旧数据。
            self._save_papers(unseen_papers)
            return unseen_papers

        except Exception as e:
            self.logger.error(self.text(f"❌ 自适应获取论文失败: {str(e)}", f"❌ Adaptive fetch failed: {str(e)}"), exc_info=True)
            raise

    def _extract_paper_info(self, result: arxiv.Result) -> Dict[str, Any]:
        """提取论文信息 / Extract paper info"""
        return {
            "id": result.entry_id.split("/")[-1],
            "arxiv_id": result.entry_id.split("/")[-1],
            "title": result.title,
            "authors": [author.name for author in result.authors],
            "abstract": result.summary.replace("\n", " ").strip(),
            "categories": result.categories,
            "primary_category": result.primary_category,
            "published": result.published.isoformat(),
            "updated": result.updated.isoformat(),
            "pdf_url": result.pdf_url,
            "entry_url": result.entry_id,
            "url": result.entry_id,
            "comment": result.comment if hasattr(result, "comment") else None,
            "journal_ref": result.journal_ref if hasattr(result, "journal_ref") else None,
            "doi": result.doi if hasattr(result, "doi") else None,
            "fetched_at": datetime.now().isoformat(),
        }

    def _save_papers(self, papers: List[Dict[str, Any]]):
        """保存论文数据 / Save papers。

        注意：即使 papers 为空，也会覆盖 latest.json，避免邮件继续读取旧论文。
        """
        papers = papers or []

        data_path = get_data_path(self.config, "papers")
        Path(data_path).mkdir(parents=True, exist_ok=True)

        date_str = get_date_string()
        filepath = f"{data_path}/papers_{date_str}.json"

        save_json(papers, filepath)
        self.logger.info(self.text(f"💾 论文数据已保存到: {filepath}", f"💾 Paper data saved to: {filepath}"))

        latest_filepath = f"{data_path}/latest.json"
        save_json({
            "date": date_str,
            "count": len(papers),
            "papers": papers,
        }, latest_filepath)
        self.logger.info(self.text(f"💾 最新数据已保存到: {latest_filepath}", f"💾 Latest data saved to: {latest_filepath}"))

    def get_paper_stats(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """获取论文统计信息 / Get paper statistics"""
        if not papers:
            return {}

        category_counts = {}
        for paper in papers:
            for category in paper["categories"]:
                category_counts[category] = category_counts.get(category, 0) + 1

        author_counts = {}
        for paper in papers:
            for author in paper["authors"]:
                author_counts[author] = author_counts.get(author, 0) + 1

        prolific_authors = {k: v for k, v in author_counts.items() if v >= 2}

        return {
            "total_papers": len(papers),
            "category_distribution": category_counts,
            "total_authors": len(author_counts),
            "prolific_authors": prolific_authors,
            "date": get_date_string(),
        }

    def print_paper_summary(self, papers: List[Dict[str, Any]]):
        """打印论文摘要 / Print paper summary"""
        if not papers:
            self.logger.info(self.text("没有找到论文", "No papers found"))
            return

        self.logger.info("\n" + "=" * 80)
        self.logger.info(self.text(f"📚 今日论文摘要 ({len(papers)} 篇)", f"📚 Today's Paper Summary ({len(papers)} papers)"))
        self.logger.info("=" * 80)

        for i, paper in enumerate(papers, 1):
            self.logger.info(f"\n[{i}] {paper['title']}")
            self.logger.info(self.text(f"    作者: {', '.join(paper['authors'][:3])}", f"    Authors: {', '.join(paper['authors'][:3])}") +
                             (" et al." if len(paper["authors"]) > 3 else ""))
            self.logger.info(self.text(f"    类别: {', '.join(paper['categories'][:3])}", f"    Categories: {', '.join(paper['categories'][:3])}"))
            self.logger.info(self.text(f"    链接: {paper['pdf_url']}", f"    Link: {paper['pdf_url']}"))
            self.logger.info(self.text(f"    摘要: {paper['abstract'][:150]}...", f"    Abstract: {paper['abstract'][:150]}..."))

        stats = self.get_paper_stats(papers)
        self.logger.info("\n" + "=" * 80)
        self.logger.info(self.text("📊 统计信息", "📊 Statistics"))
        self.logger.info("=" * 80)
        self.logger.info(self.text(f"总论文数: {stats['total_papers']}", f"Total papers: {stats['total_papers']}"))
        self.logger.info(self.text(f"总作者数: {stats['total_authors']}", f"Total authors: {stats['total_authors']}"))

        if stats.get("prolific_authors"):
            self.logger.info(self.text("\n高产作者 (2篇以上):", "\nProlific authors (2+ papers):"))
            for author, count in sorted(stats["prolific_authors"].items(), key=lambda x: x[1], reverse=True)[:5]:
                self.logger.info(self.text(f"  - {author}: {count} 篇", f"  - {author}: {count} papers"))

        self.logger.info(self.text("\n类别分布:", "\nCategory distribution:"))
        for category, count in sorted(stats["category_distribution"].items(), key=lambda x: x[1], reverse=True):
            self.logger.info(self.text(f"  - {category}: {count} 篇", f"  - {category}: {count} papers"))

        self.logger.info("=" * 80 + "\n")


def main():
    """测试函数"""
    from src.utils import load_config, load_env, setup_logging

    load_env()
    config = load_config()
    setup_logging(config)

    fetcher = ArxivFetcher(config)
    adaptive_enabled = config.get("adaptive_fetch", {}).get("enabled", False)
    dedupe_enabled = config.get("dedupe", {}).get("enabled", True)

    if adaptive_enabled and dedupe_enabled:
        state_path = config.get("dedupe", {}).get("state_path", "data/state/papers_state.json")
        papers = fetcher.fetch_papers_adaptive(state_path=state_path)
    else:
        papers = fetcher.fetch_papers(days_back=2)

    if papers:
        fetcher.print_paper_summary(papers)


if __name__ == "__main__":
    main()
