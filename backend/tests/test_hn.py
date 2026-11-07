# backend/tests/test_hn.py
from scrapers.hn_scraper import HackerNewsScraper
from tools.hn_tools import _extract_hn_story_id, _clean_comment_html


def test_hn_id_extraction():
    assert _extract_hn_story_id(12345) == 12345
    assert _extract_hn_story_id("12345") == 12345
    assert _extract_hn_story_id("hn:12345") == 12345
    assert _extract_hn_story_id("https://news.ycombinator.com/item?id=12345") == 12345
    assert _extract_hn_story_id("invalid") is None


def test_clean_comment_html():
    sample_html = "<p>Great project! Check out <a href='https://example.com'>this link</a>.</p><p>Second line <i>italic</i></p>"
    clean = _clean_comment_html(sample_html)
    assert "Great project!" in clean
    assert "Second line italic" in clean
    assert "<p>" not in clean
    assert "<a" not in clean


def test_hn_scraper_init():
    scraper = HackerNewsScraper(max_age_hours=12.0, min_score=50, limit=15)
    assert scraper.source_name == "hacker_news"
    assert scraper.max_age_hours == 12.0
    assert scraper.min_score == 50
    assert scraper.limit == 15
