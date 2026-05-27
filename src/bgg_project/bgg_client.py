from __future__ import annotations

import logging
import time
from typing import Any

import requests


class BGGClient:
    """Small BGG XML API client with auth, throttling, and simple retries."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        use_environment_proxies: bool = True,
        timeout_seconds: int = 30,
        min_seconds_between_requests: int = 5,
        max_retries: int = 4,
        retry_backoff_seconds: int = 10,
        logger: logging.Logger | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.min_seconds_between_requests = min_seconds_between_requests
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.trust_env = use_environment_proxies
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/xml",
                "User-Agent": "bgg-project-academic-research/0.1",
            }
        )
        self._last_request_monotonic: float | None = None

    def _respect_rate_limit(self) -> None:
        if self._last_request_monotonic is None:
            return
        elapsed = time.monotonic() - self._last_request_monotonic
        wait_seconds = self.min_seconds_between_requests - elapsed
        if wait_seconds > 0:
            self.logger.info("Sleeping %.2f seconds to respect BGG rate limits.", wait_seconds)
            time.sleep(wait_seconds)

    def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        for attempt in range(1, self.max_retries + 1):
            self._respect_rate_limit()
            self.logger.info("Requesting %s with params=%s", url, params)
            response = self.session.get(url, params=params, timeout=self.timeout_seconds)
            self._last_request_monotonic = time.monotonic()

            if response.status_code == 202:
                delay = self._compute_retry_delay(response, attempt=attempt, minimum_delay=self.retry_backoff_seconds)
                self.logger.warning(
                    "BGG queued the request with HTTP 202. Retrying in %s seconds.",
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code in {429, 500, 503}:
                delay = self._compute_retry_delay(
                    response,
                    attempt=attempt,
                    minimum_delay=max(self.retry_backoff_seconds * 2, self.min_seconds_between_requests * 2),
                )
                self.logger.warning(
                    "BGG returned HTTP %s. Retrying in %s seconds.",
                    response.status_code,
                    delay,
                )
                time.sleep(delay)
                continue

            response.raise_for_status()
            return response.text

        raise requests.HTTPError(
            f"BGG request failed after {self.max_retries} attempts: {url} {params}"
        )

    def _compute_retry_delay(
        self,
        response: requests.Response,
        *,
        attempt: int,
        minimum_delay: int,
    ) -> int:
        retry_after_header = response.headers.get("Retry-After")
        retry_after_seconds: int | None = None
        if retry_after_header:
            try:
                retry_after_seconds = int(float(retry_after_header))
            except ValueError:
                retry_after_seconds = None
        return max(minimum_delay * attempt, retry_after_seconds or 0)

    def get_hot_items(self, item_type: str = "boardgame") -> str:
        return self._request("hot", params={"type": item_type})

    def get_things(self, item_ids: list[int], stats: bool = True) -> str:
        if not item_ids:
            raise ValueError("item_ids must not be empty.")
        if len(item_ids) > 20:
            raise ValueError("BGG /thing endpoint accepts at most 20 ids per request.")

        params: dict[str, Any] = {"id": ",".join(str(item_id) for item_id in item_ids)}
        if stats:
            params["stats"] = 1
        return self._request("thing", params=params)

    def get_thing_ratingcomments(
        self,
        item_id: int,
        *,
        page: int = 1,
        page_size: int | None = None,
    ) -> str:
        params: dict[str, Any] = {
            "id": item_id,
            "ratingcomments": 1,
            "page": page,
        }
        if page_size is not None:
            params["pagesize"] = page_size
        return self._request("thing", params=params)

    def get_plays_for_item(
        self,
        item_id: int,
        *,
        page: int = 1,
        item_type: str = "thing",
    ) -> str:
        return self._request(
            "plays",
            params={"id": item_id, "type": item_type, "page": page},
        )

    def get_collection_for_user(
        self,
        username: str,
        *,
        rated: bool = False,
        stats: bool = False,
    ) -> str:
        params: dict[str, Any] = {"username": username}
        if rated:
            params["rated"] = 1
        if stats:
            params["stats"] = 1
        return self._request("collection", params=params)
