import base64
import logging
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
MD_SUFFIX = ".md"


@dataclass
class DiffResult:
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    @property
    def upsert_paths(self) -> list[str]:
        return self.added + self.modified


class GitHubClient:
    """GitHub API経由でリポジトリの差分・ファイル内容を取得する。"""

    def __init__(self, token: str, repo: str):
        self._repo = repo
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_latest_commit(self, ref: str = "HEAD") -> str:
        """デフォルトブランチの最新コミットハッシュを取得する。"""
        url = f"{GITHUB_API_BASE}/repos/{self._repo}/commits/{ref}"
        resp = requests.get(url, headers=self._headers)
        resp.raise_for_status()
        return resp.json()["sha"]

    def get_compare(self, base: str, head: str) -> DiffResult:
        """2つのコミット間の差分ファイルを取得する。"""
        diff = DiffResult()
        page = 1

        while True:
            url = (
                f"{GITHUB_API_BASE}/repos/{self._repo}"
                f"/compare/{base}...{head}?per_page=100&page={page}"
            )
            resp = requests.get(url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

            for f in data.get("files", []):
                filename = f["filename"]
                if not filename.endswith(MD_SUFFIX):
                    continue

                status = f["status"]
                if status == "added":
                    diff.added.append(filename)
                elif status == "modified":
                    diff.modified.append(filename)
                elif status == "removed":
                    diff.deleted.append(filename)
                elif status == "renamed":
                    if f.get("previous_filename", "").endswith(MD_SUFFIX):
                        diff.deleted.append(f["previous_filename"])
                    diff.added.append(filename)

            if len(data.get("files", [])) < 100:
                break
            page += 1

        logger.info(
            "Diff %s...%s: +%d ~%d -%d md files",
            base[:8],
            head[:8],
            len(diff.added),
            len(diff.modified),
            len(diff.deleted),
        )
        return diff

    def get_all_md_files(self, ref: str = "HEAD") -> list[str]:
        """リポジトリ内の全.mdファイルパスを取得する（初回同期用）。"""
        url = (
            f"{GITHUB_API_BASE}/repos/{self._repo}"
            f"/git/trees/{ref}?recursive=1"
        )
        resp = requests.get(url, headers=self._headers)
        resp.raise_for_status()
        tree = resp.json().get("tree", [])
        return [
            item["path"]
            for item in tree
            if item["type"] == "blob" and item["path"].endswith(MD_SUFFIX)
        ]

    def get_file_content(self, path: str, ref: str = "HEAD") -> str:
        """GitHub API経由でファイル内容を取得する。"""
        url = f"{GITHUB_API_BASE}/repos/{self._repo}/contents/{path}?ref={ref}"
        try:
            resp = requests.get(url, headers=self._headers)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", path, e)
            return ""
        data = resp.json()
        if data.get("encoding") == "base64" and data.get("content"):
            return base64.b64decode(data["content"]).decode(
                "utf-8", errors="replace"
            )
        return ""
