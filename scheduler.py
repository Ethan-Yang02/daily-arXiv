"""
定时调度器 / Scheduled runner

使用 APScheduler 实现每日自动运行 /
Use APScheduler to run daily jobs automatically
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径 / Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz
import traceback

from src.utils import load_config, load_env, setup_logging, load_json, pick_text
from src.notifier import EmailNotifier
from src.utils_1.push_dedupe import mark_papers_as_pushed
from main import main as run_daily_task


NO_PUSH_STATUSES = {
    "no_new_papers",
    "no_selected_papers",
    "no_matching_papers",
}


def _extract_items(obj, preferred_keys=("papers", "summaries", "data", "items", "results")):
    """兼容 list、{'papers': [...]}, {'summaries': [...]}, {'id': {...}} 等多种 JSON 结构"""
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]

    if isinstance(obj, dict):
        for key in preferred_keys:
            value = obj.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

        values = list(obj.values())
        if values and all(isinstance(x, dict) for x in values):
            return values

    return []


def _normalize_authors(authors):
    if not authors:
        return []
    if isinstance(authors, str):
        return [authors]

    result = []
    for a in authors:
        if isinstance(a, dict):
            name = a.get("name", "")
            if name:
                result.append(name)
        else:
            result.append(str(a))
    return result


def _get_summary_text(summary_item):
    """把单篇 summary 结构压成适合邮件展示的文本"""
    if not isinstance(summary_item, dict):
        return ""

    s = (
        summary_item.get("summary")
        or summary_item.get("chinese_summary")
        or summary_item.get("zh_summary")
        or summary_item.get("content")
        or summary_item.get("analysis")
        or ""
    )

    if isinstance(s, dict):
        parts = []
        for label, key in [
            ("核心创新", "key_innovation"),
            ("主要方法", "main_method"),
            ("实验结果", "main_results"),
            ("研究意义", "significance"),
            ("局限性", "limitations"),
        ]:
            value = s.get(key)
            if value:
                parts.append(f"{label}: {value}")
        return "\n".join(parts)

    return str(s) if s else ""


def _resolve_max_email_papers(config):
    """解析邮件最多展示论文数。all/none/0/-1 表示不限制。"""
    value = config.get("email_digest", {}).get("max_papers", "all")
    if value is None:
        return None
    if str(value).strip().lower() in {"all", "none", "0", "-1"}:
        return None
    try:
        value = int(value)
        return value if value > 0 else None
    except Exception:
        return None


def _build_digest_items(papers, summaries, max_email_papers=None):
    digest_items = []
    papers_for_email = papers if max_email_papers is None else papers[:max_email_papers]

    for i, paper in enumerate(papers_for_email):
        summary_text = _get_summary_text(summaries[i]) if i < len(summaries) else ""

        categories = paper.get("categories") or []
        if isinstance(categories, str):
            categories = [categories]

        digest_items.append({
            "title": paper.get("title", "Untitled"),
            "url": paper.get("url") or paper.get("entry_id") or "",
            "pdf_url": paper.get("pdf_url") or "",
            "category": paper.get("primary_category") or paper.get("category") or (categories[0] if categories else ""),
            "categories": categories,
            "authors": _normalize_authors(paper.get("authors")),
            "published": paper.get("published") or paper.get("published_date") or "",
            "abstract": paper.get("abstract") or paper.get("summary") or "",
            "ai_summary": summary_text,
            "llm_filter": paper.get("llm_filter", {}),
        })

    return digest_items


def _send_success_email(logger, notifier, duration, text):
    """根据本次 run_status 发送正常日报或 0 篇空日报。"""
    current_config = load_config()
    run_status = load_json(Path("data/run_status/latest.json")) or {}
    status = run_status.get("status", "")

    # 如果今天没有新论文，绝对不要读取旧 summaries/latest.json 或 analysis/latest.json。
    # 否则会把上一次推送过的 analysis/summary 又发一遍。
    if status in NO_PUSH_STATUSES or int(run_status.get("final_papers_count", -1) or -1) == 0 and status != "success":
        stats_info = {
            "papers_count": 0,
            "summaries_count": 0,
            "categories_count": 0,
            "keywords_count": 0,
            "no_new_papers": True,
            "run_status": status,
            "status_message": run_status.get("message") or "今天没有新的论文需要推送，因此本次推送论文数量为 0。",
            "fetched_count": run_status.get("fetched_count", 0),
            "skipped_seen_count": run_status.get("skipped_seen_count", 0),
            "new_papers_count": run_status.get("new_papers_count", 0),
            "filtered_papers_count": run_status.get("filtered_papers_count", 0),
            "final_papers_count": 0,
        }

        email_ok = notifier.send_notification(
            success=True,
            stats=stats_info,
            duration=duration,
            papers=[],
            analysis={},
        )

        if logger:
            logger.info(text(
                "本次没有新论文，已发送 0 篇空日报，不会重复推送旧论文",
                "No new papers this run; sent empty digest and did not re-push old papers"
            ))

        return email_ok

    # 正常日报：只在本次确实有最终论文时才读取 latest summaries/analysis
    papers_raw = load_json(Path("data/papers/latest.json")) or {}
    summaries_raw = load_json(Path("data/summaries/latest.json")) or {}
    analysis_raw = load_json(Path("data/analysis/latest.json")) or {}

    papers = _extract_items(papers_raw, preferred_keys=("papers", "data", "items", "results"))
    summaries = _extract_items(summaries_raw, preferred_keys=("summaries", "papers", "data", "items", "results"))

    statistics = analysis_raw.get("statistics", {}) if isinstance(analysis_raw, dict) else {}
    keywords = analysis_raw.get("keywords", []) if isinstance(analysis_raw, dict) else []

    stats_info = {
        "papers_count": len(papers),
        "summaries_count": len(summaries),
        "categories_count": statistics.get(
            "total_categories",
            len({
                p.get("primary_category")
                or p.get("category")
                or (p.get("categories", [""])[0] if isinstance(p.get("categories"), list) and p.get("categories") else "")
                for p in papers
                if isinstance(p, dict)
            } - {""})
        ),
        "keywords_count": len(keywords),
        "no_new_papers": False,
        "run_status": status,
        "status_message": run_status.get("message", ""),
        "fetched_count": run_status.get("fetched_count", 0),
        "skipped_seen_count": run_status.get("skipped_seen_count", 0),
        "new_papers_count": run_status.get("new_papers_count", len(papers)),
        "filtered_papers_count": run_status.get("filtered_papers_count", len(papers)),
        "final_papers_count": run_status.get("final_papers_count", len(papers)),
    }

    digest_items = _build_digest_items(papers, summaries, max_email_papers=_resolve_max_email_papers(current_config))

    # 保险：如果 latest 里没有论文，也发 0 篇空日报，而不是让邮件模板展示旧 analysis。
    if not digest_items:
        stats_info.update({
            "papers_count": 0,
            "summaries_count": 0,
            "categories_count": 0,
            "keywords_count": 0,
            "no_new_papers": True,
            "status_message": "本次 latest.json 中没有新论文，因此本次推送论文数量为 0。",
            "final_papers_count": 0,
        })

        return notifier.send_notification(
            success=True,
            stats=stats_info,
            duration=duration,
            papers=[],
            analysis={},
        )

    email_ok = notifier.send_notification(
        success=True,
        stats=stats_info,
        duration=duration,
        papers=digest_items,
        analysis=analysis_raw,
    )

    # 只有邮件发送成功后，才标记为已推送
    if email_ok and current_config.get("dedupe", {}).get("enabled", True):
        dedupe_config = current_config.get("dedupe", {})
        state_path = dedupe_config.get("state_path", "data/state/papers_state.json")
        keep_days = int(dedupe_config.get("keep_days", 180))

        pushed_count = mark_papers_as_pushed(
            digest_items,
            state_path=state_path,
            keep_days=keep_days,
        )

        if logger:
            logger.info(text(
                f"已将 {pushed_count} 篇论文标记为已推送",
                f"Marked {pushed_count} papers as pushed"
            ))

    return email_ok


def scheduled_task(logger=None, notifier=None, language="zh"):
    """定时执行的任务 / Scheduled task entry."""
    start_time = datetime.now()
    lang = str(language).strip().lower()
    text = (lambda zh, en: en) if lang.startswith("en") else (lambda zh, en: zh)

    print("\n" + "=" * 60)
    print(f"⏰ Scheduled task triggered - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    if logger:
        logger.info(text(f"定时任务开始执行 - {start_time}", f"Scheduled task started - {start_time}"))

    try:
        # 执行主任务 / Run main workflow
        run_daily_task()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print(text("✅ 任务执行成功！", "✅ Task completed successfully!"))
        print(text(f"⏱️  耗时: {duration:.2f} 秒", f"⏱️  Duration: {duration:.2f} seconds"))
        print(text(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}", f"🕐 Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}"))
        print("=" * 60 + "\n")

        if logger:
            logger.info(text(f"定时任务执行成功，耗时 {duration:.2f} 秒", f"Scheduled task succeeded, took {duration:.2f} seconds"))

        # 发送成功通知 / Send success notification
        if notifier:
            try:
                _send_success_email(logger, notifier, duration, text)
            except Exception as e:
                if logger:
                    logger.warning(text(
                        f"发送邮件通知失败: {str(e)}",
                        f"Failed to send email notification: {str(e)}"
                    ), exc_info=True)

        return True

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "=" * 60)
        print(text("❌ 任务执行失败！", "❌ Task execution failed!"))
        print(text(f"⏱️  耗时: {duration:.2f} 秒", f"⏱️  Duration: {duration:.2f} seconds"))
        print(text(f"🔴 错误: {str(e)}", f"🔴 Error: {str(e)}"))
        print("=" * 60)
        print(text("\n详细错误信息:", "\nDetailed error information:"))
        traceback.print_exc()
        print()

        if logger:
            logger.error(text(f"定时任务执行失败: {str(e)}", f"Scheduled task failed: {str(e)}"), exc_info=True)

        # 发送失败通知 / Send failure notification
        if notifier:
            try:
                notifier.send_notification(
                    success=False,
                    error_msg=f"{str(e)}\n\n{traceback.format_exc()}",
                    duration=duration,
                )
            except Exception as email_error:
                if logger:
                    logger.warning(text(
                        f"发送邮件通知失败: {str(email_error)}",
                        f"Failed to send email notification: {str(email_error)}"
                    ))

        return False


def main():
    """主函数 / Main function"""
    # 加载配置 / Load configuration
    load_env()
    config = load_config()
    logger = setup_logging(config)
    text = lambda zh, en: pick_text(config, zh, en)

    scheduler_config = config.get("scheduler", {})

    if not scheduler_config.get("enabled", False):
        logger.warning(text(
            "定时调度未启用，请在 config.yaml 中设置 scheduler.enabled = true",
            "Scheduler is disabled. Set scheduler.enabled = true in config.yaml"
        ))
        print(text("\n⚠️  定时调度未启用", "\n⚠️  Scheduler is disabled"))
        print(text("请在 config/config.yaml 中设置:", "Please set this in config/config.yaml:"))
        print("  scheduler:")
        print("    enabled: true")
        return

    # 获取配置 / Read scheduler config
    run_time = scheduler_config.get("run_time", "09:00")
    timezone = scheduler_config.get("timezone", "Asia/Shanghai")
    run_on_start = scheduler_config.get("run_on_start", True)

    # 解析运行时间 / Parse run time
    try:
        hour, minute = map(int, run_time.split(":"))
    except ValueError:
        logger.error(text(
            f"无效的运行时间格式: {run_time}，应为 HH:MM 格式",
            f"Invalid run_time format: {run_time}, expected HH:MM"
        ))
        print(text(f"❌ 无效的运行时间格式: {run_time}", f"❌ Invalid run_time format: {run_time}"))
        print(text("请使用 HH:MM 格式，例如: 09:00", "Please use HH:MM format, e.g. 09:00"))
        return

    tz = pytz.timezone(timezone)

    # 创建调度器 / Create scheduler
    scheduler = BlockingScheduler(timezone=tz)

    # 添加定时任务 / Register scheduled job
    trigger = CronTrigger(
        hour=hour,
        minute=minute,
        timezone=tz,
    )

    # 初始化邮件通知器 / Initialize email notifier
    notifier = None
    notification_config = scheduler_config.get("notification", {})
    if notification_config.get("enabled", False):
        email_config = notification_config.get("email", {})
        email_config["_language"] = config.get("app", {}).get("language", "zh")
        notifier = EmailNotifier(email_config)
        logger.info(text("邮件通知已启用", "Email notification enabled"))

    scheduler.add_job(
        scheduled_task,
        trigger=trigger,
        args=[logger, notifier, config.get("app", {}).get("language", "zh")],
        id="daily_arxiv_task",
        name="Daily arXiv Paper Fetching",
        max_instances=1,
        coalesce=True,
    )

    # 计算下次运行时间 / Calculate next run time
    next_run = datetime.now(tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= datetime.now(tz):
        from datetime import timedelta
        next_run += timedelta(days=1)

    logger.info(text(
        f"定时调度器已启动，将在每天 {run_time} ({timezone}) 执行任务",
        f"Scheduler started, will run daily at {run_time} ({timezone})"
    ))
    print("\n" + "=" * 60)
    print(text("⏰ Daily arXiv 定时调度器", "⏰ Daily arXiv Scheduler"))
    print("=" * 60)
    print(text(f"📅 执行时间: 每天 {run_time}", f"📅 Run Time: daily at {run_time}"))
    print(text(f"🌍 时区: {timezone}", f"🌍 Timezone: {timezone}"))
    print(text(f"⏭️  下次运行: {next_run.strftime('%Y-%m-%d %H:%M:%S')}", f"⏭️  Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"))
    print(text(f"🔄 启动时立即运行: {'是' if run_on_start else '否'}", f"🔄 Run on start: {'yes' if run_on_start else 'no'}"))
    print("=" * 60)
    print(text("\n按 Ctrl+C 停止调度器\n", "\nPress Ctrl+C to stop scheduler\n"))

    # 启动时立即运行一次 / Run once at startup if enabled
    if run_on_start:
        logger.info(text("启动时立即执行任务...", "Running task on startup..."))
        print(text("🚀 启动时立即执行任务...\n", "🚀 Running task on startup...\n"))
        scheduled_task(logger, notifier, config.get("app", {}).get("language", "zh"))

    try:
        # 启动调度器 / Start scheduler loop
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info(text("定时调度器已停止", "Scheduler stopped"))
        print("\n" + "=" * 60)
        print(text("👋 定时调度器已停止", "👋 Scheduler stopped"))
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
