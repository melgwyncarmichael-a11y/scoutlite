#!/usr/bin/env python3
"""
ScoutLite v2 (exploratory, standalone): player/team name -> recent Reddit posts -> basic sentiment.

Kept separate from scoutlite.py on purpose -- proven independently before any wiring together,
same as FBref was. Reddit's robots.txt disallows scraping site-wide (Disallow: / for all
agents), so this goes through Reddit's official Data API (free, non-commercial tier) via PRAW,
OAuth-authenticated, read-only mode. No scraping involved.

Requires a registered Reddit "script" app (https://www.reddit.com/prefs/apps) for
REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in .env.
"""
import argparse
import os
import sys
from pathlib import Path

import praw
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

SUBREDDITS = "soccer+football"
POST_LIMIT = 15


def get_reddit_client() -> praw.Reddit:
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "scoutlite/0.1"),
    )
    reddit.read_only = True
    return reddit


def fetch_posts(reddit: praw.Reddit, query: str, limit: int = POST_LIMIT):
    subreddit = reddit.subreddit(SUBREDDITS)
    return list(subreddit.search(query, sort="new", time_filter="month", limit=limit))


def main():
    parser = argparse.ArgumentParser(
        description="Pull recent Reddit posts for a player/team and score basic sentiment"
    )
    parser.add_argument("query", help="Player or team name, e.g. 'Erling Haaland'")
    args = parser.parse_args()

    if not os.environ.get("REDDIT_CLIENT_ID") or not os.environ.get("REDDIT_CLIENT_SECRET"):
        sys.exit("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set. Add them to .env in this project folder.")

    reddit = get_reddit_client()
    print(f"Searching r/{SUBREDDITS} for '{args.query}'...")
    posts = fetch_posts(reddit, args.query)

    if not posts:
        print("No posts found.")
        return

    analyzer = SentimentIntensityAnalyzer()
    print(f"\nFound {len(posts)} posts:\n")
    scores = []
    for post in posts:
        text = f"{post.title} {post.selftext}"
        score = analyzer.polarity_scores(text)["compound"]
        scores.append(score)
        print(f"[{score:+.2f}] {post.title}  (r/{post.subreddit.display_name}, {post.score} upvotes)")

    avg = sum(scores) / len(scores)
    print(f"\nAverage sentiment: {avg:+.2f} (-1 very negative, +1 very positive)")


if __name__ == "__main__":
    main()
