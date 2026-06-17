"""Apify Instagram scraper for ARTART.

Reads `references.json` for target accounts, calls apify/instagram-post-scraper,
normalizes the response, downloads each post's images to
`references/<username>/assets/`, and writes metadata to
`references/<username>/posts.jsonl`.

Never scrape Instagram from @artart.today's logged-in session. Always go
through Apify — see PLAN.md Phase 1 for the reasoning.

Run:
    python3 src/scrapers/apify_ig.py
    python3 src/scrapers/apify_ig.py --limit 5 --accounts dy1.mag bizucafe
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
REFS_PATH = REPO_ROOT / "references.json"
REFERENCES_DIR = REPO_ROOT / "references"

POST_SCRAPER_ACTOR = "apify~instagram-post-scraper"
SYNC_ENDPOINT = (
    "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"
)


def load_env(path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def call_actor(actor: str, token: str, payload: dict) -> list[dict]:
    url = SYNC_ENDPOINT.format(actor=actor, token=token)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def _child_image_urls(raw: dict) -> list[str]:
    """Collect every slide image URL from a carousel/sidecar post.

    IG carousel posts expose slides as either `childPosts` (list of dicts with
    their own displayUrl) or `images` (flat list of URLs). Handle both.
    Falls back to [displayUrl] for single-image posts.
    """
    urls: list[str] = []
    for child in raw.get("childPosts") or []:
        u = child.get("displayUrl") if isinstance(child, dict) else None
        if u:
            urls.append(u)
    for u in raw.get("images") or []:
        if isinstance(u, str) and u not in urls:
            urls.append(u)
    if not urls and raw.get("displayUrl"):
        urls.append(raw["displayUrl"])
    return urls


def normalize_post(raw: dict) -> dict:
    """Pick the fields we actually care about for ARTART analysis.

    Note: Instagram does NOT expose share counts through any public scraper —
    Apify included. Only the post owner sees shares via IG Insights.
    """
    return {
        "id": raw.get("id"),
        "shortCode": raw.get("shortCode"),
        "url": raw.get("url"),
        "type": raw.get("type"),
        "owner": raw.get("ownerUsername"),
        "ownerFullName": raw.get("ownerFullName"),
        "caption": raw.get("caption") or "",
        "hashtags": raw.get("hashtags") or [],
        "mentions": raw.get("mentions") or [],
        "taggedUsers": [u.get("username") for u in (raw.get("taggedUsers") or []) if u],
        "likes": raw.get("likesCount"),
        "comments": raw.get("commentsCount"),
        "timestamp": raw.get("timestamp"),
        "displayUrl": raw.get("displayUrl"),
        "_sourceImageUrls": _child_image_urls(raw),
        "dimensions": {
            "w": raw.get("dimensionsWidth"),
            "h": raw.get("dimensionsHeight"),
        },
    }


def download_image(url: str, dest: pathlib.Path) -> bool:
    """Download a single IG CDN URL to disk. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
        return dest.stat().st_size > 1024  # reject truncated / error responses
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  ! failed {dest.name}: {e}", file=sys.stderr)
        return False


def persist_post(post: dict, account_dir: pathlib.Path) -> dict:
    """Download images for one post and mutate the post dict with local paths.

    Removes the ephemeral _sourceImageUrls field and replaces it with
    `localImages`: a list of repo-relative paths to the downloaded files.
    """
    assets_dir = account_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    short = post.get("shortCode") or "unknown"
    source_urls: list[str] = post.pop("_sourceImageUrls", [])
    local_paths: list[str] = []
    for idx, url in enumerate(source_urls):
        dest = assets_dir / f"{short}_{idx:02d}.jpg"
        if dest.exists() and dest.stat().st_size > 1024:
            local_paths.append(str(dest.relative_to(REPO_ROOT)))
            continue
        if download_image(url, dest):
            local_paths.append(str(dest.relative_to(REPO_ROOT)))
    post["localImages"] = local_paths
    post["imageCount"] = len(local_paths)
    return post


def scrape_accounts(
    token: str,
    usernames: list[str],
    limit: int,
    strict: bool = True,
    download_images: bool = True,
) -> dict[str, list[dict]]:
    """Scrape recent posts, group by owner.

    Returns {username: [post, ...]}. If download_images=True, also downloads
    each post's images to references/<owner>/assets/ and adds localImages.
    Skip downloads (download_images=False) when you only need metadata —
    much faster for monitoring/ranking use cases.
    """
    payload = {"username": usernames, "resultsLimit": limit}
    raw = call_actor(POST_SCRAPER_ACTOR, token, payload)
    wanted = {u.lower() for u in usernames}
    normalized = [normalize_post(p) for p in raw]
    if strict:
        normalized = [p for p in normalized if (p["owner"] or "").lower() in wanted]

    by_owner: dict[str, list[dict]] = {}
    for post in normalized:
        owner = post["owner"] or "unknown"
        by_owner.setdefault(owner, []).append(post)

    for owner, posts in by_owner.items():
        account_dir = REFERENCES_DIR / owner
        account_dir.mkdir(parents=True, exist_ok=True)
        if download_images:
            print(f"  {owner}: downloading images for {len(posts)} posts...")
            for post in posts:
                persist_post(post, account_dir)
        else:
            for post in posts:
                post.pop("_sourceImageUrls", None)
                post["localImages"] = []
                post["imageCount"] = 0

    return by_owner


def write_posts_jsonl(posts: list[dict], account_dir: pathlib.Path) -> pathlib.Path:
    """Write normalized posts to references/<owner>/posts.jsonl (append-safe).

    Deduplicates by shortCode — newer scrape wins.
    """
    out = account_dir / "posts.jsonl"
    existing: dict[str, dict] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
                existing[p.get("shortCode") or p.get("id") or ""] = p
            except json.JSONDecodeError:
                continue
    for p in posts:
        existing[p.get("shortCode") or p.get("id") or ""] = p
    merged = sorted(
        existing.values(), key=lambda p: p.get("timestamp") or "", reverse=True
    )
    with out.open("w", encoding="utf-8") as f:
        for p in merged:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="ARTART IG scraper (Apify)")
    parser.add_argument("--limit", type=int, default=None, help="posts per account")
    parser.add_argument("--accounts", nargs="*", default=None, help="override accounts")
    parser.add_argument("--no-strict", action="store_true", help="keep collab posts")
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    token = env.get("APIFY_TOKEN") or os.environ.get("APIFY_TOKEN")
    if not token:
        print("ERROR: APIFY_TOKEN not found in .env or environment", file=sys.stderr)
        return 2

    refs = json.loads(REFS_PATH.read_text())
    ig_cfg = refs.get("instagram", {})
    accounts_cfg = ig_cfg.get("accounts", [])
    usernames = args.accounts or [a["username"] for a in accounts_cfg]
    limit = args.limit or ig_cfg.get("scrape_config", {}).get("results_per_account", 10)

    if not usernames:
        print("ERROR: no accounts to scrape (check references.json)", file=sys.stderr)
        return 2

    print(f"Scraping {len(usernames)} accounts, up to {limit} posts each: {usernames}")
    by_owner = scrape_accounts(token, usernames, limit, strict=not args.no_strict)

    print()
    total = 0
    for owner, posts in sorted(by_owner.items()):
        account_dir = REFERENCES_DIR / owner
        out_path = write_posts_jsonl(posts, account_dir)
        total += len(posts)
        img_total = sum(len(p.get("localImages") or []) for p in posts)
        print(
            f"  {owner}: {len(posts)} posts, {img_total} images -> "
            f"{out_path.relative_to(REPO_ROOT)}"
        )
    print(f"\nDone. {total} posts across {len(by_owner)} account(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
