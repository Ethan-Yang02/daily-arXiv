"""LLM-based paper relevance filter."""

import json
import re
import logging
from typing import List, Dict, Any

from src.summarizer.llm_factory import LLMClientFactory


class LLMPaperFilter:
    """Use LLM to judge whether papers match the user's research interests."""

    SYSTEM_PROMPT = """你是一个严谨的学术论文筛选助手。
你需要根据用户关注方向，判断 arXiv 论文是否值得保留。

输出要求：
1. 只输出 JSON，不要输出 Markdown。
2. JSON 格式必须是：
{
  "relevant": true 或 false,
  "score": 0.0 到 1.0,
  "topic": "简短主题标签",
  "reason": "一句话说明判断理由"
}
3. score 表示论文与用户关注方向的相关度。
4. 如果只是普通大模型、普通视觉模型、普通 benchmark，而没有效率、压缩、加速、推理优化、长上下文效率等贡献，应判为 false。
"""

    USER_PROMPT_TEMPLATE = """用户关注方向：
{topic}

请判断下面论文是否相关：

标题：
{title}

类别：
{categories}

摘要：
{abstract}

请只输出 JSON。
"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.filter_config = config.get("llm_filter", {})
        self.enabled = self.filter_config.get("enabled", False)
        self.threshold = float(self.filter_config.get("threshold", 0.65))
        self.max_selected = int(self.filter_config.get("max_selected", 20))
        self.fail_open = bool(self.filter_config.get("fail_open", True))
        self.topic = self.filter_config.get("topic", "")
        self.logger = logging.getLogger("daily_arxiv.llm_filter")

        self.llm_client = LLMClientFactory.create_client(config)

    def filter_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.enabled:
            self.logger.info("LLM 过滤未启用，跳过")
            return papers

        if not papers:
            return []

        self.logger.info("=" * 60)
        self.logger.info(f"开始 LLM 智能过滤，共 {len(papers)} 篇候选论文")
        self.logger.info(f"过滤阈值: {self.threshold}")
        self.logger.info(f"最多保留: {self.max_selected}")
        self.logger.info("=" * 60)

        selected = []

        for i, paper in enumerate(papers, 1):
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            categories = ", ".join(paper.get("categories", []))

            try:
                prompt = self.USER_PROMPT_TEMPLATE.format(
                    topic=self.topic,
                    title=title,
                    categories=categories,
                    abstract=abstract,
                )

                raw = self.llm_client.generate(
                    prompt=prompt,
                    system_prompt=self.SYSTEM_PROMPT,
                )

                decision = self._parse_json(raw)
                relevant = bool(decision.get("relevant", False))
                score = float(decision.get("score", 0.0))
                reason = decision.get("reason", "")
                topic = decision.get("topic", "")

                paper["llm_filter"] = {
                    "relevant": relevant,
                    "score": score,
                    "topic": topic,
                    "reason": reason,
                }

                if relevant and score >= self.threshold:
                    selected.append(paper)
                    self.logger.info(
                        f"✓ [{i}/{len(papers)}] 保留 score={score:.2f}: {title[:70]}..."
                    )
                    self.logger.info(f"  理由: {reason}")
                else:
                    self.logger.info(
                        f"× [{i}/{len(papers)}] 过滤 score={score:.2f}: {title[:70]}..."
                    )

            except Exception as e:
                self.logger.warning(f"LLM 过滤失败: {title[:70]}... error={e}")

                paper["llm_filter"] = {
                    "relevant": self.fail_open,
                    "score": 0.0,
                    "topic": "filter_error",
                    "reason": f"LLM filter failed: {e}",
                }

                if self.fail_open:
                    selected.append(paper)

            if len(selected) >= self.max_selected:
                self.logger.info(f"已达到 max_selected={self.max_selected}，停止筛选")
                break

        self.logger.info("=" * 60)
        self.logger.info(f"LLM 过滤完成：{len(papers)} 篇候选，保留 {len(selected)} 篇")
        self.logger.info("=" * 60)

        return selected

    def _parse_json(self, text: str) -> Dict[str, Any]:
        text = text.strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError(f"LLM output is not JSON: {text[:200]}")

        return json.loads(match.group(0))