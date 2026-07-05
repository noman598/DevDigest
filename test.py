from backend.scrapers.github_trending import GitHubTrendingScraper
s = GitHubTrendingScraper(since='daily')
items = s.fetch()
print(f'Got {len(items)} repos')
print(items[0])