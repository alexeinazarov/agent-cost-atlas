from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from email.message import Message
from typing import Any

from .config import GitHubConfig
from .models import QueryStat

JsonObject = dict[str, Any]

# These statuses describe a repository state we can represent without making
# the whole sweep unreliable. Other statuses are surfaced to the engine and
# recorded as collection failures.
TOLERATED_README_STATUSES = frozenset({404})
TOLERATED_COMMIT_STATUSES = frozenset({404, 409})
TRANSIENT_HTTP_STATUSES = frozenset({500, 502, 503, 504})


class GitHubApiError(RuntimeError):
    """Raised when the GitHub API cannot be queried reliably.

    ``status`` carries the HTTP status when the failure came from a response.
    ``rate_limited`` distinguishes throttling from ordinary per-repository
    failures; throttling must never be silently converted into missing data.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        rate_limited: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.rate_limited = rate_limited

    def is_tolerable(self, statuses: frozenset[int]) -> bool:
        return self.status in statuses and not self.rate_limited


@dataclass(frozen=True, slots=True)
class ReadmeDocument:
    text: str
    sha: str | None


class GitHubClient:
    def __init__(self, config: GitHubConfig, token: str | None = None) -> None:
        self._config = config
        raw_token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self._token = raw_token.strip()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self._config.user_agent,
            "X-GitHub-Api-Version": self._config.api_version,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @staticmethod
    def _is_rate_limited(status: int, headers: Message, body: str) -> bool:
        """Recognize primary and secondary GitHub rate-limit responses."""
        if status == 429:
            return True
        if status != 403:
            return False
        if headers.get("Retry-After") or headers.get("X-RateLimit-Remaining") == "0":
            return True

        message = body.casefold()
        return "secondary rate limit" in message or "rate limit exceeded" in message

    @staticmethod
    def _rate_limit_wait_seconds(headers: Message, attempt: int) -> float:
        retry_after = headers.get("Retry-After")
        if retry_after:
            with suppress(ValueError):
                return max(1.0, float(retry_after))

        reset = headers.get("X-RateLimit-Reset")
        if headers.get("X-RateLimit-Remaining") == "0" and reset:
            with suppress(ValueError):
                return max(1.0, float(reset) - time.time() + 1.0)

        # GitHub's documented fallback for a secondary limit without either
        # header is at least one minute, followed by increasing delays.
        return min(300.0, 60.0 * (2 ** max(0, attempt - 1)))

    @staticmethod
    def _transient_wait_seconds(attempt: int) -> float:
        return min(30.0, float(2 ** max(0, attempt - 1)))

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> JsonObject:
        url = f"{self._config.api_base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers=self._headers())
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self._config.timeout_seconds,
                ) as response:
                    payload = json.load(response)
                    if not isinstance(payload, dict):
                        raise GitHubApiError(f"Unexpected non-object response from {url}")
                    return payload
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                rate_limited = self._is_rate_limited(exc.code, exc.headers, body)

                if rate_limited and attempt < self._config.max_retries:
                    delay = self._rate_limit_wait_seconds(exc.headers, attempt)
                    print(
                        f"GitHub rate limit response; sleeping {delay:.1f}s",
                        flush=True,
                    )
                    time.sleep(delay)
                    continue

                if exc.code in TRANSIENT_HTTP_STATUSES and attempt < self._config.max_retries:
                    delay = self._transient_wait_seconds(attempt)
                    print(
                        f"GitHub transient HTTP {exc.code}; sleeping {delay:.1f}s",
                        flush=True,
                    )
                    time.sleep(delay)
                    continue

                raise GitHubApiError(
                    f"GitHub API returned HTTP {exc.code} for {url}: {body[:300]}",
                    status=exc.code,
                    rate_limited=rate_limited,
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < self._config.max_retries:
                    time.sleep(self._transient_wait_seconds(attempt))
                    continue
                break

        raise GitHubApiError(f"GitHub request failed for {url}: {last_error}") from last_error

    def search_repositories(self, query: str, mode: str) -> tuple[list[JsonObject], QueryStat]:
        repositories: list[JsonObject] = []
        total_count = 0
        incomplete = False
        pages_retrieved = 0

        for page in range(1, self._config.max_pages_per_query + 1):
            params: dict[str, str | int] = {
                "q": query,
                "per_page": self._config.per_page,
                "page": page,
            }
            if mode == "updated":
                params.update({"sort": "updated", "order": "desc"})
            elif mode == "stars":
                params.update({"sort": "stars", "order": "desc"})
            elif mode != "best_match":
                raise ValueError(f"Unsupported search mode: {mode}")

            payload = self._get("/search/repositories", params)
            items = payload.get("items") or []
            if not isinstance(items, list):
                raise GitHubApiError("GitHub search response did not contain an items list")

            total_count = int(payload.get("total_count") or 0)
            incomplete = incomplete or bool(payload.get("incomplete_results"))
            repositories.extend(item for item in items if isinstance(item, dict))
            pages_retrieved += 1

            if len(items) < self._config.per_page:
                break
            time.sleep(self._config.search_delay_seconds)

        time.sleep(self._config.search_delay_seconds)
        exhausted_pages = pages_retrieved >= self._config.max_pages_per_query
        return repositories, QueryStat(
            query=query,
            mode=mode,
            total_count=total_count,
            retrieved=len(repositories),
            pages_retrieved=pages_retrieved,
            incomplete_results=incomplete,
            capped_by_page_limit=exhausted_pages and total_count > len(repositories),
        )

    def fetch_readme(self, full_name: str) -> ReadmeDocument:
        try:
            payload = self._get(f"/repos/{full_name}/readme")
        except GitHubApiError as exc:
            if exc.is_tolerable(TOLERATED_README_STATUSES):
                return ReadmeDocument(text="", sha=None)
            raise

        text = ""
        content = payload.get("content")
        if payload.get("encoding") == "base64" and isinstance(content, str):
            try:
                text = base64.b64decode(content, validate=False).decode("utf-8", "replace")
            except (ValueError, UnicodeError):
                text = ""

        time.sleep(self._config.core_delay_seconds)
        sha = payload.get("sha")
        return ReadmeDocument(text=text, sha=sha if isinstance(sha, str) else None)

    def fetch_head_sha(self, full_name: str, default_branch: str) -> str | None:
        branch = urllib.parse.quote(default_branch, safe="")
        try:
            payload = self._get(f"/repos/{full_name}/commits/{branch}")
        except GitHubApiError as exc:
            # Empty repositories have no head commit and GitHub returns 409.
            if exc.is_tolerable(TOLERATED_COMMIT_STATUSES):
                return None
            raise

        time.sleep(self._config.core_delay_seconds)
        sha = payload.get("sha")
        return sha if isinstance(sha, str) else None
