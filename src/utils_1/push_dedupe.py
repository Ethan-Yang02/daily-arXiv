"""论文去重工具：避免重复 LLM 过滤和重复邮件推送"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta


def normalize_arxiv_id(value):
    """从 arXiv URL / entry_id / arxiv_id 中提取稳定 ID，并去掉版本号 v1/v2"""
    if not value:
        return ""

    text = str(value).strip()

    patterns = [
        r"arxiv\.org/abs/([^?#/]+)",
        r"arxiv\.org/pdf/([^?#/]+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            text = m.group(1)
            break

    text = text.replace(".pdf", "")
    text = text.strip()
    text = re.sub(r"v\d+$", "", text)

    return text


def get_paper_id(paper):
    """从 paper dict 中拿到唯一论文 ID"""
    if not isinstance(paper, dict):
        return ""

    candidates = [
        paper.get("arxiv_id"),
        paper.get("id"),
        paper.get("entry_id"),
        paper.get("url"),
        paper.get("pdf_url"),
    ]

    for value in candidates:
        pid = normalize_arxiv_id(value)
        if pid:
            return pid

    title = str(paper.get("title", "")).strip().lower()
    if title:
        return "title:" + re.sub(r"\s+", " ", title)

    return ""


def load_state(state_path):
    path = Path(state_path)
    if not path.exists():
        return {
            "seen": {},
            "pushed": {},
            "updated_at": None,
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {
                "seen": {},
                "pushed": {},
                "updated_at": None,
            }

        # 兼容之前只有 pushed 的旧格式
        if "seen" not in data:
            data["seen"] = {}
        if "pushed" not in data:
            data["pushed"] = {}

        return data

    except Exception:
        return {
            "seen": {},
            "pushed": {},
            "updated_at": None,
        }


def save_state(state_path, state):
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    state["updated_at"] = datetime.now().isoformat(timespec="seconds")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def prune_state(state, keep_days=180):
    cutoff = datetime.now() - timedelta(days=int(keep_days))

    for key in ["seen", "pushed"]:
        records = state.get(key, {})
        if not isinstance(records, dict):
            state[key] = {}
            continue

        new_records = {}
        for pid, info in records.items():
            if not isinstance(info, dict):
                new_records[pid] = info
                continue

            ts = info.get("seen_at") or info.get("pushed_at")
            if not ts:
                new_records[pid] = info
                continue

            try:
                dt = datetime.fromisoformat(ts)
                if dt >= cutoff:
                    new_records[pid] = info
            except Exception:
                new_records[pid] = info

        state[key] = new_records

    return state


def filter_unseen_papers(papers, state_path):
    """
    过滤已经爬过的论文。
    用在 LLM 过滤之前，避免重复 LLM 调用。
    """
    state = load_state(state_path)
    seen = state.get("seen", {})

    new_papers = []
    skipped_seen = []

    for paper in papers:
        pid = get_paper_id(paper)
        if pid and pid in seen:
            skipped_seen.append(paper)
        else:
            new_papers.append(paper)

    return new_papers, skipped_seen


def mark_papers_as_seen(papers, state_path, keep_days=180):
    """
    只要本次从 arXiv 抓到了，就标记为 seen。
    用于避免以后重复走 LLM 过滤。
    """
    state = load_state(state_path)
    seen = state.setdefault("seen", {})

    now = datetime.now().isoformat(timespec="seconds")

    for paper in papers:
        pid = get_paper_id(paper)
        if not pid:
            continue

        seen[pid] = {
            "seen_at": now,
            "title": paper.get("title", ""),
            "url": paper.get("url") or paper.get("entry_id") or "",
            "category": paper.get("primary_category") or paper.get("category") or "",
        }

    state = prune_state(state, keep_days=keep_days)
    save_state(state_path, state)

    return len(papers)


def filter_unpushed_papers(papers, state_path):
    """
    过滤已经邮件推送过的论文。
    通常用于邮件发送之前的保险。
    """
    state = load_state(state_path)
    pushed = state.get("pushed", {})

    new_papers = []
    skipped_pushed = []

    for paper in papers:
        pid = get_paper_id(paper)
        if pid and pid in pushed:
            skipped_pushed.append(paper)
        else:
            new_papers.append(paper)

    return new_papers, skipped_pushed


def mark_papers_as_pushed(papers, state_path, keep_days=180):
    """邮件发送成功后，把本次论文标记为 pushed"""
    state = load_state(state_path)
    pushed = state.setdefault("pushed", {})

    now = datetime.now().isoformat(timespec="seconds")

    for paper in papers:
        pid = get_paper_id(paper)
        if not pid:
            continue

        pushed[pid] = {
            "pushed_at": now,
            "title": paper.get("title", ""),
            "url": paper.get("url") or paper.get("entry_id") or "",
            "category": paper.get("primary_category") or paper.get("category") or "",
        }

    state = prune_state(state, keep_days=keep_days)
    save_state(state_path, state)

    return len(papers)