"""邮件通知模块：发送 Daily arXiv 研究日报"""

import os
import re
import ssl
import html
import smtplib
import logging
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart


class EmailNotifier:
    """邮件通知器"""

    def __init__(self, config):
        self.smtp_server = config.get("smtp_server", "smtp.gmail.com")
        self.smtp_port = int(config.get("smtp_port", 587))
        self.sender = config.get("sender", "")
        self.password = os.getenv("EMAIL_PASSWORD", config.get("password", ""))
        self.recipients = config.get("recipients", [])
        self.on_success = config.get("on_success", True)
        self.on_failure = config.get("on_failure", True)
        self.language = str(config.get("_language", "zh")).strip().lower()
        self.text = (lambda zh, en: en) if self.language.startswith("en") else (lambda zh, en: zh)
        self.logger = logging.getLogger(__name__)

    def send_notification(
        self,
        success=True,
        stats=None,
        error_msg=None,
        duration=0,
        papers=None,
        analysis=None,
    ):
        """发送通知邮件"""
        stats = stats or {}
        papers = papers or []
        analysis = analysis or {}

        if success and not self.on_success:
            return True
        if not success and not self.on_failure:
            return True

        if not self.sender or not self.recipients:
            self.logger.warning(self.text(
                "邮件发送者或收件人未配置，跳过邮件通知",
                "Email sender or recipients are not configured, skipping notification"
            ))
            return False

        if not self.password:
            self.logger.warning(self.text(
                "邮件密码未配置，跳过邮件通知",
                "Email password is not configured, skipping notification"
            ))
            return False

        try:
            msg = MIMEMultipart("related")
            msg["From"] = self.sender
            msg["To"] = ", ".join(self.recipients)
            msg["Subject"] = self._get_subject(success, stats, papers, analysis)

            alt = MIMEMultipart("alternative")
            msg.attach(alt)

            text_content = self._generate_text_content(success, stats, error_msg, duration, papers, analysis)
            html_content = self._generate_html_content(success, stats, error_msg, duration, papers, analysis)

            alt.attach(MIMEText(text_content, "plain", "utf-8"))
            alt.attach(MIMEText(html_content, "html", "utf-8"))

            # 内嵌词云图。如果邮箱客户端屏蔽图片，正文仍然可读。
            wordcloud_path = ""
            if isinstance(analysis, dict):
                wordcloud_path = analysis.get("wordcloud_path", "") or ""

            if wordcloud_path and Path(wordcloud_path).exists():
                try:
                    with open(wordcloud_path, "rb") as f:
                        img = MIMEImage(f.read())
                    img.add_header("Content-ID", "<wordcloud>")
                    img.add_header("Content-Disposition", "inline", filename=Path(wordcloud_path).name)
                    msg.attach(img)
                except Exception as e:
                    self.logger.warning(f"词云图片内嵌失败: {e}")

            context = ssl.create_default_context()

            if self.smtp_port in (465, 994):
                with smtplib.SMTP_SSL(
                    self.smtp_server,
                    self.smtp_port,
                    timeout=30,
                    context=context,
                ) as server:
                    server.login(self.sender, self.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(
                    self.smtp_server,
                    self.smtp_port,
                    timeout=30,
                ) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.sender, self.password)
                    server.send_message(msg)

            self.logger.info(self.text(
                f"邮件通知发送成功: {', '.join(self.recipients)}",
                f"Email notification sent successfully: {', '.join(self.recipients)}"
            ))
            return True

        except Exception as e:
            self.logger.error(self.text(
                f"邮件发送失败: {str(e)}",
                f"Failed to send email: {str(e)}"
            ), exc_info=True)
            return False

    def _get_subject(self, success, stats=None, papers=None, analysis=None):
        date_str = datetime.now().strftime("%Y-%m-%d")
        stats = stats or {}

        if success:
            if stats.get("no_new_papers"):
                return self.text(
                    f"📭 Daily arXiv 研究日报 - {date_str} - 今日新论文 0 篇",
                    f"📭 Daily arXiv Research Digest - {date_str} - 0 new papers"
                )

            paper_count = stats.get("papers_count", len(papers or []))
            return self.text(
                f"📚 Daily arXiv 研究日报 - {date_str} - {paper_count} 篇",
                f"📚 Daily arXiv Research Digest - {date_str} - {paper_count} papers"
            )

        return self.text(
            f"❌ Daily arXiv 任务失败 - {date_str}",
            f"❌ Daily arXiv Task Failed - {date_str}"
        )

    def _clean_text(self, value, max_len=None):
        """清理 Markdown / LaTeX，让邮件可读"""
        if value is None:
            return ""

        if isinstance(value, list):
            value = ", ".join(str(x) for x in value)

        text = str(value)

        # 去代码块、行内代码、Markdown 强调
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = text.replace("**", "").replace("__", "")

        # 去 Markdown 标题符号
        text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)

        # 简化常见 LaTeX
        text = text.replace("\\(", "").replace("\\)", "")
        text = text.replace("\\[", "").replace("\\]", "")
        text = text.replace("$", "")
        text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
        text = re.sub(r"\\mathbf\{([^{}]*)\}", r"\1", text)
        text = re.sub(r"\\mathrm\{([^{}]*)\}", r"\1", text)
        text = re.sub(r"\\emph\{([^{}]*)\}", r"\1", text)
        text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", text)
        text = text.replace("\\times", "×")
        text = text.replace("\\cdot", "·")
        text = text.replace("\\rightarrow", "→")
        text = text.replace("\\to", "→")
        text = text.replace("\\leq", "≤")
        text = text.replace("\\geq", "≥")

        # 压缩空白
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = text.strip()

        if max_len and len(text) > max_len:
            text = text[:max_len].rstrip() + "..."

        return text

    def _esc(self, value, max_len=None):
        return html.escape(self._clean_text(value, max_len=max_len))

    def _format_authors(self, authors, max_authors=5):
        if not authors:
            return ""

        if isinstance(authors, str):
            return authors

        result = []
        for a in authors[:max_authors]:
            if isinstance(a, dict):
                name = a.get("name", "")
                if name:
                    result.append(name)
            else:
                result.append(str(a))

        if len(authors) > max_authors:
            result.append("等")

        return ", ".join(result)

    def _split_markdown_lines(self, content, max_len=1800):
        """把 Markdown 分析文本拆成适合 HTML 邮件展示的段落和列表"""
        content = self._clean_text(content or "", max_len=max_len)
        if not content:
            return ""

        html_parts = []
        list_open = False

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            line = re.sub(r"^\d+\.\s*", "", line)
            is_bullet = line.startswith("- ") or line.startswith("* ") or line.startswith("• ")

            if is_bullet:
                if not list_open:
                    html_parts.append("<ul style='margin:8px 0 0 18px;padding:0;'>")
                    list_open = True
                html_parts.append(
                    f"<li style='margin:7px 0;line-height:1.65;'>{self._esc(line[2:], 700)}</li>"
                )
            else:
                if list_open:
                    html_parts.append("</ul>")
                    list_open = False
                html_parts.append(
                    f"<p style='margin:9px 0;line-height:1.7;'>{self._esc(line, 900)}</p>"
                )

        if list_open:
            html_parts.append("</ul>")

        return "".join(html_parts)

    def _generate_text_content(self, success, stats, error_msg, duration, papers, analysis):
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "Daily arXiv Research Digest",
            "=" * 60,
            f"执行时间: {date_str}",
            f"执行结果: {'成功' if success else '失败'}",
            f"执行耗时: {duration:.2f} 秒",
            "",
        ]

        if not success:
            lines.append("错误信息:")
            lines.append(error_msg or "")
            return "\n".join(lines)

        llm_analysis = analysis.get("llm_analysis", {}) if isinstance(analysis, dict) else {}
        statistics = analysis.get("statistics", {}) if isinstance(analysis, dict) else {}

        lines.extend([
            f"论文数量: {stats.get('papers_count', len(papers))}",
            f"总结数量: {stats.get('summaries_count', 0)}",
            f"研究类别: {stats.get('categories_count', 0)}",
            f"执行耗时: {duration:.2f} 秒",
            "",
        ])

        if stats.get("no_new_papers"):
            lines.extend([
                "今日新论文数量: 0",
                f"抓取候选论文数: {stats.get('fetched_count', 0)}",
                f"已爬过/重复论文数: {stats.get('skipped_seen_count', 0)}",
                f"LLM 筛选前新论文数: {stats.get('new_papers_count', 0)}",
                "",
                stats.get("status_message") or "今天没有新的论文需要推送，因此本次不会重复推送旧论文。",
                "",
            ])
            return "\n".join(lines)

        if llm_analysis.get("analysis_summary"):
            lines.append("分析总结:")
            lines.append(self._clean_text(llm_analysis.get("analysis_summary"), 1200))
            lines.append("")

        if llm_analysis.get("hotspots"):
            lines.append("研究热点:")
            lines.append(self._clean_text(llm_analysis.get("hotspots"), 1500))
            lines.append("")

        if llm_analysis.get("trends"):
            lines.append("技术趋势:")
            lines.append(self._clean_text(llm_analysis.get("trends"), 1500))
            lines.append("")

        if llm_analysis.get("future_directions"):
            lines.append("未来方向:")
            lines.append(self._clean_text(llm_analysis.get("future_directions"), 1200))
            lines.append("")

        if llm_analysis.get("research_ideas"):
            lines.append("创新研究想法:")
            lines.append(self._clean_text(llm_analysis.get("research_ideas"), 1600))
            lines.append("")

        category_distribution = statistics.get("category_distribution", {})
        if category_distribution:
            lines.append("类别分布:")
            for name, value in list(category_distribution.items())[:10]:
                lines.append(f"- {name}: {value}")
            lines.append("")

        top_words = statistics.get("top_words", {})
        if top_words:
            lines.append("高频词 Top 10:")
            for name, value in list(top_words.items())[:10]:
                lines.append(f"- {name}: {value}")
            lines.append("")

        lines.append("今日重点论文:")
        for i, paper in enumerate(papers, 1):
            lines.append(f"{i}. {self._clean_text(paper.get('title', 'Untitled'))}")
            if paper.get("category"):
                lines.append(f"   类别: {paper.get('category')}")
            authors = self._format_authors(paper.get("authors"))
            if authors:
                lines.append(f"   作者: {authors}")
            if paper.get("url"):
                lines.append(f"   arXiv: {paper.get('url')}")
            summary = paper.get("ai_summary") or paper.get("abstract") or ""
            if summary:
                lines.append(f"   摘要: {self._clean_text(summary, 500)}")
            lines.append("")

        return "\n".join(lines)

    def _generate_html_content(self, success, stats, error_msg, duration, papers, analysis):
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status_color = "#16a34a" if success else "#dc2626"
        status_bg = "#ecfdf5" if success else "#fef2f2"
        status_text = "任务成功" if success else "任务失败"
        status_icon = "✅" if success else "❌"

        html_doc = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width">
  <title>Daily arXiv Research Digest</title>
</head>
<body style="margin:0;padding:0;background:#f5f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans SC','Microsoft YaHei',sans-serif;color:#111827;">
  <div style="max-width:880px;margin:0 auto;padding:28px 14px;">

    <div style="background:linear-gradient(135deg,#0f172a,#334155);border-radius:22px;padding:30px;color:#ffffff;box-shadow:0 14px 34px rgba(15,23,42,.22);">
      <div style="font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#cbd5e1;margin-bottom:10px;">Daily arXiv Research Digest</div>
      <div style="font-size:30px;line-height:1.25;font-weight:850;margin-bottom:12px;">
        📚 每日论文研究情报
      </div>
      <div style="font-size:15px;color:#e5e7eb;">
        执行时间: {self._esc(date_str)} &nbsp;·&nbsp; 耗时: {duration:.1f}s
      </div>
    </div>

    <div style="margin-top:18px;background:{status_bg};border:1px solid {status_color}22;border-left:6px solid {status_color};border-radius:16px;padding:16px 18px;">
      <div style="font-size:18px;font-weight:850;color:{status_color};">
        {status_icon} {status_text}
      </div>
      <div style="font-size:14px;color:#374151;margin-top:6px;">
        {'下面是本次 arXiv 自动抓取、筛选、总结和趋势分析结果。' if success else '任务执行失败，下面是错误信息。'}
      </div>
    </div>
"""

        if not success:
            html_doc += f"""
    <div style="margin-top:20px;background:#ffffff;border:1px solid #fecaca;border-radius:18px;padding:18px;">
      <div style="font-size:18px;font-weight:850;color:#b91c1c;margin-bottom:10px;">错误信息</div>
      <pre style="white-space:pre-wrap;background:#f9fafb;border-radius:12px;padding:14px;color:#374151;font-size:13px;line-height:1.55;">{self._esc(error_msg or "")}</pre>
    </div>
"""
            return self._wrap_html_end(html_doc)

        analysis = analysis or {}
        statistics = analysis.get("statistics", {}) if isinstance(analysis, dict) else {}
        llm_analysis = analysis.get("llm_analysis", {}) if isinstance(analysis, dict) else {}
        wordcloud_path = analysis.get("wordcloud_path", "") if isinstance(analysis, dict) else ""

        paper_count = stats.get("papers_count", len(papers))
        summaries_count = stats.get("summaries_count", 0)
        categories_count = stats.get("categories_count", statistics.get("total_categories", 0))

        html_doc += f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:18px;border-spacing:0;">
      <tr>
        <td style="width:25%;padding:6px;">{self._stat_card("论文", paper_count, "📄")}</td>
        <td style="width:25%;padding:6px;">{self._stat_card("总结", summaries_count, "🧠")}</td>
        <td style="width:25%;padding:6px;">{self._stat_card("类别", categories_count, "🏷️")}</td>
        <td style="width:25%;padding:6px;">{self._stat_card("耗时", f"{duration:.0f}s", "⏱️")}</td>
      </tr>
    </table>
"""

        if stats.get("no_new_papers"):
            html_doc += self._render_no_new_papers_block(stats)
            return self._wrap_html_end(html_doc)

        html_doc += self._render_analysis_summary(llm_analysis)

        if wordcloud_path:
            html_doc += """
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:18px;margin-top:16px;box-shadow:0 6px 18px rgba(15,23,42,.05);">
      <div style="font-size:18px;font-weight:850;color:#111827;margin-bottom:10px;">☁️ 关键词词云</div>
      <img src="cid:wordcloud" alt="wordcloud" style="width:100%;max-width:820px;border-radius:14px;border:1px solid #e5e7eb;display:block;">
      <div style="font-size:12px;color:#9ca3af;margin-top:8px;">如果图片没有显示，请查看邮件附件或查看 Web 页面。</div>
    </div>
"""

        html_doc += self._render_distribution_bars(
            statistics.get("category_distribution", {}),
            "类别分布",
            "📊"
        )

        html_doc += self._render_distribution_bars(
            statistics.get("top_words", {}),
            "高频词 Top 10",
            "🔠",
            limit=10
        )

        html_doc += self._render_analysis_block(
            "当前研究热点",
            llm_analysis.get("hotspots", ""),
            "🔥",
            1800,
        )

        html_doc += self._render_analysis_block(
            "技术趋势与演进",
            llm_analysis.get("trends", ""),
            "📈",
            1800,
        )

        html_doc += self._render_analysis_block(
            "未来发展方向",
            llm_analysis.get("future_directions", ""),
            "🚀",
            1600,
        )

        html_doc += self._render_analysis_block(
            "创新研究想法",
            llm_analysis.get("research_ideas", ""),
            "💡",
            2200,
        )

        html_doc += """
    <div style="margin-top:24px;margin-bottom:10px;">
      <div style="font-size:22px;font-weight:850;color:#111827;">📄 今日重点论文</div>
      <div style="font-size:14px;color:#6b7280;margin-top:4px;">
        展示筛选后的重点论文。完整内容可查看本地 Web 页面或 data 目录。
      </div>
    </div>
"""

        if papers:
            for idx, paper in enumerate(papers, 1):
                html_doc += self._paper_card(idx, paper)
        else:
            html_doc += """
    <div style="margin-top:20px;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;padding:22px;text-align:center;color:#6b7280;">
      本次没有可展示的论文。
    </div>
"""

        return self._wrap_html_end(html_doc)

    def _wrap_html_end(self, html_doc):
        html_doc += """
    <div style="margin-top:26px;text-align:center;color:#9ca3af;font-size:12px;">
      这是一封自动发送的邮件，请勿回复。
    </div>

  </div>
</body>
</html>
"""
        return html_doc

    def _stat_card(self, label, value, icon):
        return f"""
          <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;padding:16px 12px;text-align:center;box-shadow:0 6px 18px rgba(15,23,42,.05);">
            <div style="font-size:22px;margin-bottom:6px;">{icon}</div>
            <div style="font-size:25px;font-weight:850;color:#111827;">{value}</div>
            <div style="font-size:13px;color:#6b7280;margin-top:4px;">{self._esc(label)}</div>
          </div>
        """

    def _render_no_new_papers_block(self, stats):
        """渲染今日 0 篇新论文的邮件页面，避免重复展示旧日报内容。"""
        message = stats.get("status_message") or "今天没有新的论文需要推送，因此本次不会重复推送旧论文。"
        fetched_count = stats.get("fetched_count", 0)
        skipped_seen_count = stats.get("skipped_seen_count", 0)
        new_papers_count = stats.get("new_papers_count", 0)
        filtered_papers_count = stats.get("filtered_papers_count", 0)
        run_status = stats.get("run_status", "")

        return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:22px;padding:28px 22px;margin-top:20px;box-shadow:0 8px 24px rgba(15,23,42,.06);text-align:center;">
      <div style="font-size:46px;line-height:1;margin-bottom:12px;">📭</div>
      <div style="font-size:24px;font-weight:900;color:#111827;margin-bottom:8px;">
        今日新论文推送数量为 0
      </div>
      <div style="font-size:15px;color:#475569;line-height:1.75;max-width:680px;margin:0 auto;">
        {self._esc(message, 500)}
      </div>
      <div style="margin-top:18px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:16px;padding:16px;text-align:left;">
        <div style="font-size:15px;font-weight:850;color:#0f172a;margin-bottom:10px;">本次去重结果</div>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-spacing:0;font-size:14px;color:#334155;">
          <tr>
            <td style="padding:7px 0;">抓取候选论文数</td>
            <td style="padding:7px 0;text-align:right;font-weight:850;">{fetched_count}</td>
          </tr>
          <tr>
            <td style="padding:7px 0;">已爬过 / 重复论文数</td>
            <td style="padding:7px 0;text-align:right;font-weight:850;">{skipped_seen_count}</td>
          </tr>
          <tr>
            <td style="padding:7px 0;">LLM 筛选前新论文数</td>
            <td style="padding:7px 0;text-align:right;font-weight:850;">{new_papers_count}</td>
          </tr>
          <tr>
            <td style="padding:7px 0;">LLM 筛选后论文数</td>
            <td style="padding:7px 0;text-align:right;font-weight:850;">{filtered_papers_count}</td>
          </tr>
          <tr>
            <td style="padding:7px 0;">运行状态</td>
            <td style="padding:7px 0;text-align:right;font-weight:850;">{self._esc(run_status or "no_new_papers", 80)}</td>
          </tr>
        </table>
      </div>
      <div style="font-size:12px;color:#94a3b8;margin-top:14px;line-height:1.6;">
        本邮件没有读取旧的 summaries/latest.json 或 analysis/latest.json，因此不会重复展示上一次已经推送过的论文和分析。
      </div>
    </div>
"""

    def _render_analysis_summary(self, llm_analysis):
        summary = llm_analysis.get("analysis_summary", "") if isinstance(llm_analysis, dict) else ""
        if not summary:
            return ""

        return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:20px;margin-top:18px;box-shadow:0 6px 18px rgba(15,23,42,.05);">
      <div style="font-size:19px;font-weight:850;color:#111827;margin-bottom:10px;">🧭 今日一句话判断</div>
      <div style="font-size:15px;line-height:1.75;color:#334155;">
        {self._split_markdown_lines(summary, max_len=1200)}
      </div>
    </div>
"""

    def _render_distribution_bars(self, distribution, title, icon="📊", limit=10):
        if not distribution or not isinstance(distribution, dict):
            return ""

        items = list(distribution.items())[:limit]
        if not items:
            return ""

        max_value = max([v for _, v in items if isinstance(v, (int, float))] or [1])

        rows = []
        for name, value in items:
            if not isinstance(value, (int, float)):
                continue

            percent = int(value / max_value * 100) if max_value else 0
            rows.append(f"""
            <div style="margin:11px 0;">
              <div style="display:flex;justify-content:space-between;font-size:13px;color:#334155;margin-bottom:5px;">
                <span>{self._esc(name, 70)}</span>
                <strong>{value}</strong>
              </div>
              <div style="height:10px;background:#e5e7eb;border-radius:999px;overflow:hidden;">
                <div style="width:{percent}%;height:10px;background:#2563eb;border-radius:999px;"></div>
              </div>
            </div>
            """)

        if not rows:
            return ""

        return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:18px;margin-top:16px;box-shadow:0 6px 18px rgba(15,23,42,.05);">
      <div style="font-size:18px;font-weight:850;color:#111827;margin-bottom:10px;">{icon} {self._esc(title)}</div>
      {''.join(rows)}
    </div>
"""

    def _render_analysis_block(self, title, content, icon="🧠", max_len=1800):
        if not content:
            return ""

        body = self._split_markdown_lines(content, max_len=max_len)
        if not body:
            return ""

        return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:18px;margin-top:16px;box-shadow:0 6px 18px rgba(15,23,42,.05);">
      <div style="font-size:18px;font-weight:850;color:#111827;margin-bottom:10px;">{icon} {self._esc(title)}</div>
      <div style="font-size:14px;line-height:1.75;color:#334155;">
        {body}
      </div>
    </div>
"""

    def _paper_card(self, idx, paper):
        title = self._esc(paper.get("title", "Untitled"), 240)
        category = self._esc(paper.get("category", ""), 80)
        published = self._esc(paper.get("published", ""), 80)
        authors = self._esc(self._format_authors(paper.get("authors")), 240)

        url = paper.get("url", "") or ""
        pdf_url = paper.get("pdf_url", "") or ""
        summary = paper.get("ai_summary") or paper.get("abstract") or ""
        summary = self._esc(summary, 900)

        llm_filter = paper.get("llm_filter", {}) or {}
        score = llm_filter.get("score")
        reason = llm_filter.get("reason", "")
        topic = llm_filter.get("topic", "")

        badges = ""

        if category:
            badges += f"""
            <span style="display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:750;margin-right:6px;">
              {category}
            </span>
            """

        if published:
            badges += f"""
            <span style="display:inline-block;background:#f1f5f9;color:#475569;border-radius:999px;padding:4px 10px;font-size:12px;margin-right:6px;">
              {published}
            </span>
            """

        if isinstance(score, (int, float)):
            badges += f"""
            <span style="display:inline-block;background:#ecfdf5;color:#047857;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:750;margin-right:6px;">
              LLM 相关度 {score:.2f}
            </span>
            """

        if topic:
            badges += f"""
            <span style="display:inline-block;background:#fff7ed;color:#c2410c;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:750;margin-right:6px;">
              {self._esc(topic, 40)}
            </span>
            """

        arxiv_button = ""
        if url:
            arxiv_button = f"""
              <a href="{html.escape(url)}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:10px;padding:9px 13px;font-size:13px;font-weight:750;margin-right:8px;">
                arXiv
              </a>
            """

        pdf_button = ""
        if pdf_url:
            pdf_button = f"""
              <a href="{html.escape(pdf_url)}" style="display:inline-block;background:#111827;color:#ffffff;text-decoration:none;border-radius:10px;padding:9px 13px;font-size:13px;font-weight:750;">
                PDF
              </a>
            """

        reason_block = ""
        if reason:
            reason_block = f"""
              <div style="margin-top:10px;color:#64748b;font-size:13px;line-height:1.55;">
                <strong>筛选理由:</strong> {self._esc(reason, 240)}
              </div>
            """

        summary_block = ""
        if summary:
            summary_block = f"""
              <div style="margin-top:13px;background:#f8fafc;border-left:4px solid #93c5fd;border-radius:10px;padding:13px 14px;color:#334155;font-size:14px;line-height:1.65;">
                <div style="font-weight:850;color:#1f2937;margin-bottom:5px;">AI 总结 / 摘要</div>
                {summary}
              </div>
            """

        return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:20px;margin:14px 0;box-shadow:0 8px 22px rgba(15,23,42,.06);">
      <div style="display:flex;align-items:flex-start;">
        <div style="min-width:34px;height:34px;border-radius:12px;background:#e0f2fe;color:#0369a1;text-align:center;line-height:34px;font-weight:900;margin-right:12px;">
          {idx}
        </div>
        <div style="flex:1;">
          <div style="font-size:18px;font-weight:850;line-height:1.35;color:#0f172a;">
            {title}
          </div>
          <div style="margin-top:9px;">{badges}</div>
          <div style="margin-top:9px;color:#64748b;font-size:13px;line-height:1.5;">{authors}</div>
          {reason_block}
          {summary_block}
          <div style="margin-top:14px;">
            {arxiv_button}
            {pdf_button}
          </div>
        </div>
      </div>
    </div>
        """


def send_test_email(config):
    """发送测试邮件"""
    notifier = EmailNotifier(config)

    test_stats = {
        "papers_count": 3,
        "summaries_count": 3,
        "categories_count": 2,
    }

    test_analysis = {
        "statistics": {
            "total_papers": 3,
            "total_categories": 2,
            "category_distribution": {"cs.LG": 2, "cs.CL": 1},
            "top_words": {"inference": 6, "compression": 5, "context": 4, "quantization": 3},
        },
        "llm_analysis": {
            "analysis_summary": "本次论文主要集中在高效推理、长上下文和模型压缩方向，反映出大模型部署成本正在成为核心研究问题。",
            "hotspots": "- KV cache 压缩与长上下文推理效率\n- 低比特量化和推理加速\n- 多模态大模型的高效部署",
            "trends": "- 从单点模型结构优化转向系统级推理优化\n- 量化、缓存压缩和注意力优化开始组合使用",
            "future_directions": "- 面向真实服务负载的端到端加速评测\n- 长上下文 MLLM 的内存压缩和动态 token 选择",
            "research_ideas": "- 设计面向 MLLM 的视觉 token 动态裁剪方法\n- 将 KV cache 压缩和 speculative decoding 联合优化",
        },
    }

    test_papers = [
        {
            "title": "Efficient Long-Context Multimodal Model Compression",
            "category": "cs.LG",
            "authors": ["Alice Wang", "Bob Chen"],
            "published": "2026-06-11",
            "url": "https://arxiv.org/abs/0000.00000",
            "pdf_url": "https://arxiv.org/pdf/0000.00000",
            "ai_summary": "提出一种面向长上下文多模态模型的压缩方法，在保持准确率的同时降低 KV cache 占用和推理延迟。",
            "llm_filter": {"score": 0.92, "topic": "long-context efficiency", "reason": "论文直接关注长上下文多模态模型的压缩和推理效率。"},
        }
    ]

    print("\n发送测试邮件...")
    success = notifier.send_notification(
        success=True,
        stats=test_stats,
        duration=120.5,
        papers=test_papers,
        analysis=test_analysis,
    )

    if success:
        print("✅ 测试邮件发送成功！")
    else:
        print("❌ 测试邮件发送失败！")

    return success