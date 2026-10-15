from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.crawler.ssrf import SSRFError, dns_pinning, validate_url_safety


async def _check_ssrf(request: httpx.Request):
    try:
        validate_url_safety(str(request.url))
    except SSRFError as error:
        raise ValueError(f"SSRF blocked: {error}")


class RobotsChecker:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.robots_url = urljoin(
            self.base_url + "/",
            "/robots.txt",
        )

        self.parser = RobotFileParser()
        self.parser.set_url(self.robots_url)

        self.loaded = False

    async def load(self) -> None:
        # Fail closed on SSRF: do not fetch robots.txt from internal hosts.
        # Let SSRFError/ValueError propagate so the crawl fails instead
        # of silently allowing all URLs.
        # DNS is pinned for the whole fetch to close the
        # validate -> connect rebinding gap.
        with dns_pinning():
            validate_url_safety(self.robots_url)

            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=10.0,
                    headers={"User-Agent": "SiteAgent/1.0"},
                    event_hooks={"request": [_check_ssrf]},
                ) as client:
                    response = await client.get(self.robots_url)

                    if response.status_code == 200:
                        self.parser.parse(
                            response.text.splitlines()
                        )
                    elif response.status_code in {401, 403}:
                        self.parser.parse(["User-agent: *", "Disallow: /"])
                    else:
                        self.parser.parse([])

            except (SSRFError, ValueError):
                raise

            except httpx.HTTPError:
                self.parser.parse([])

        self.loaded = True

    def can_fetch(
        self,
        url: str,
        user_agent: str = "*",
    ) -> bool:
        if not self.loaded:
            raise RuntimeError(
                "RobotsChecker must be loaded before checking URLs"
            )

        return self.parser.can_fetch(
            user_agent,
            url,
        )
