#!/usr/bin/env python3
"""
ScoutLite v2 (exploratory, standalone): player/team name -> recent news headlines.

Kept separate from scoutlite.py and reddit_sentiment.py on purpose -- proven independently
before any wiring together. Uses NewsAPI's free "Developer" tier: 100 requests/day, dev/test
use only (not licensed for production or internal production use), 1-month article lookback.
robots.txt disallows /v1/ and /v2/ from crawlers, but that's standard index-avoidance for an
API-first service, not a restriction on calling the API with a registered key.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

API_URL = "https://newsapi.org/v2/everything"
LOOKBACK_DAYS = 28  # stay safely inside the Developer tier's 1-month limit
ARTICLE_LIMIT = 15


def fetch_articles(query: str, api_key: str, limit: int = ARTICLE_LIMIT) -> list[dict]:
    from_date = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    response = requests.get(
        API_URL,
        params={
            "q": query,
            "from": from_date,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": limit,
            "apiKey": api_key,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("articles", [])


def main():
    parser = argparse.ArgumentParser(
        description="Pull recent news headlines for a player/team and score basic sentiment"
    )
    parser.add_argument("query", help="Player or team name, e.g. 'Erling Haaland'")
    args = parser.parse_args()

    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        sys.exit("NEWSAPI_KEY is not set. Add it to .env in this project folder.")

    print(f"Fetching news for '{args.query}' (last {LOOKBACK_DAYS} days)...")
    articles = fetch_articles(args.query, api_key)

    if not articles:
        print("No articles found.")
        return

    analyzer = SentimentIntensityAnalyzer()
    print(f"\nFound {len(articles)} articles:\n")
    scores = []
    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '') or ''}"
        score = analyzer.polarity_scores(text)["compound"]
        scores.append(score)
        source = article.get("source", {}).get("name", "unknown")
        published = article.get("publishedAt", "")[:10]
        print(f"[{score:+.2f}] {article.get('title', '')}  ({source}, {published})")

    avg = sum(scores) / len(scores)
    print(f"\nAverage sentiment: {avg:+.2f} (-1 very negative, +1 very positive)")


if __name__ == "__main__":
    main()
