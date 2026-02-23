import logging
import re
from datetime import date, datetime
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)


def parse_markdown(file_path: str, raw_content: str) -> dict:
    """Markdownファイルをパースし、Frontmatterと本文を分離する。

    Returns:
        {
            "file_path": str,
            "frontmatter": dict,
            "content": str,
            "title": str,
            "tags": list[str],
        }
    """
    try:
        post = frontmatter.loads(raw_content)
        fm = _normalize_frontmatter(dict(post.metadata) if post.metadata else {})
        content = post.content.strip()
    except Exception as e:
        logger.warning("Frontmatter parse failed for %s: %s", file_path, e)
        fm = {}
        content = raw_content.strip()

    title = _extract_title(fm, content, file_path)
    tags = _extract_tags(fm)

    p = Path(file_path)
    parts = p.parts
    return {
        "file_path": file_path,
        "dir_path": str(p.parent) if str(p.parent) != "." else "",
        "file_name": p.stem,
        "category": parts[0] if len(parts) > 1 else "",
        "frontmatter": fm,
        "content": content,
        "title": title,
        "tags": tags,
    }


def _extract_title(fm: dict, content: str, file_path: str) -> str:
    """タイトル優先順位: Frontmatter title > 本文H1 > ファイル名"""
    if fm.get("title"):
        return str(fm["title"])

    h1_match = re.match(r"^#\s+(.+)$", content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    return Path(file_path).stem


def _normalize_frontmatter(fm: dict) -> dict:
    """Frontmatter値をJSONシリアライズ可能な型に変換する。"""
    normalized = {}
    for key, value in fm.items():
        if isinstance(value, (datetime, date)):
            normalized[key] = value.isoformat()
        elif isinstance(value, dict):
            normalized[key] = _normalize_frontmatter(value)
        elif isinstance(value, list):
            normalized[key] = [
                v.isoformat() if isinstance(v, (datetime, date)) else v
                for v in value
            ]
        else:
            normalized[key] = value
    return normalized


def _extract_tags(fm: dict) -> list[str]:
    """Frontmatterからタグを抽出する。"""
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, list):
        return [str(t) for t in tags]
    return []
