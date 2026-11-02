"""Bounded GET-only JSON transport; no stale-cache fallback or credential logging."""
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import monotonic, sleep
import requests


class ReadOnlyJsonClient:
    def __init__(self, *, session=None, attempts=3, timeout=10, min_interval=1.0,
                 cache_ttl=30, max_requests=100, max_wait=55, clock=monotonic, sleeper=sleep):
        if not 1 <= attempts <= 5 or timeout <= 0 or min_interval < 0 or cache_ttl < 0 or max_requests < 1:
            raise ValueError('Invalid transport limits')
        self.session = session or requests.Session()
        self.attempts, self.timeout = attempts, timeout
        self.min_interval, self.cache_ttl = min_interval, cache_ttl
        self.max_requests, self.max_wait = max_requests, max_wait
        self.clock, self.sleep = clock, sleeper
        self.cache, self.last_request = {}, None
        self.requests = self.cache_hits = self.retries = self.errors = 0

    def _wait(self, seconds):
        if seconds > self.max_wait:
            raise RuntimeError('provider_backoff_exceeds_budget')
        if seconds > 0:
            self.sleep(seconds)

    def get_json(self, url, *, params=None):
        key = (url, tuple(sorted((params or {}).items())))
        cached = self.cache.get(key)
        if cached and self.clock() - cached[0] < self.cache_ttl:
            self.cache_hits += 1
            return deepcopy(cached[1])
        for attempt in range(self.attempts):
            if self.requests >= self.max_requests:
                raise RuntimeError('request_budget_exhausted')
            if self.last_request is not None:
                self._wait(max(0, self.min_interval - (self.clock() - self.last_request)))
            self.requests += 1
            self.last_request = self.clock()
            delay = 2 ** attempt
            try:
                response = self.session.get(url, params=params, timeout=self.timeout, allow_redirects=False)
                status = response.status_code
                if status == 200:
                    payload = response.json()
                    self.cache[key] = (self.clock(), deepcopy(payload))
                    return payload
                if status not in (429, 500, 502, 503, 504):
                    raise ValueError(f'http_status_{status}')
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            delay = max(delay, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError):
                            pass
            except (requests.Timeout, requests.ConnectionError):
                pass
            except (ValueError, requests.RequestException):
                self.errors += 1
                raise RuntimeError('provider_response_invalid') from None
            if attempt + 1 < self.attempts:
                self.retries += 1
                self._wait(delay)
        self.errors += 1
        raise RuntimeError('provider_retries_exhausted')

    def metrics(self):
        return dict(requests=self.requests, cache_hits=self.cache_hits,
                    retries=self.retries, errors=self.errors)
