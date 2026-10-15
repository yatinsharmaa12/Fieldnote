import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.robots import RobotsChecker


@pytest.mark.anyio
async def test_robots_allows_public_page():
    checker = RobotsChecker("https://example.com")

    response = MagicMock(status_code=200, text="User-agent: *\nAllow: /")
    with patch("app.crawler.robots.validate_url_safety"), patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        await checker.load()

    assert checker.can_fetch(
        "https://example.com/"
    )


@pytest.mark.anyio
async def test_robots_checker_requires_load():
    checker = RobotsChecker("https://example.com")

    with pytest.raises(RuntimeError):
        checker.can_fetch(
            "https://example.com/"
        )


def test_robots_is_always_loaded_from_the_origin():
    assert RobotsChecker("https://example.com/products/page").robots_url == "https://example.com/robots.txt"


@pytest.mark.anyio
async def test_forbidden_robots_disallows_crawling():
    checker = RobotsChecker("https://example.com")
    with patch("app.crawler.robots.validate_url_safety"), patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=403))):
        await checker.load()
    assert not checker.can_fetch("https://example.com/", user_agent="SiteAgent/1.0")
