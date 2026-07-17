from __future__ import annotations

import datetime as dt
import unittest

from src.monitor.life_radar import (
    build_life_profile,
    classify_topics,
    collect_today_candidates,
    extract_source_handles,
    editorial_multiplier,
    risk_multiplier,
    select_balanced,
    token_similarity,
)


NOW = dt.datetime(2026, 7, 17, 0, 0, tzinfo=dt.timezone.utc)


def post(
    code: str,
    caption: str,
    likes: int,
    *,
    age_hours: int = 72,
    owner: str = "artart.life",
    post_type: str = "Sidecar",
) -> dict:
    timestamp = (NOW - dt.timedelta(hours=age_hours)).isoformat()
    return {
        "shortCode": code,
        "url": f"https://www.instagram.com/p/{code}/",
        "owner": owner,
        "type": post_type,
        "caption": caption,
        "hashtags": [],
        "mentions": [],
        "taggedUsers": [],
        "likes": likes,
        "comments": 0,
        "timestamp": timestamp,
    }


class ClassificationTests(unittest.TestCase):
    def test_animal_beats_generic_daily_words(self) -> None:
        candidate = post("A", "일상에서 만난 아기 물범과 수달", 100)
        self.assertEqual(classify_topics(candidate)[0], "animal_cute")

    def test_film_is_kept_separate_from_drama(self) -> None:
        candidate = post("F", "극장에서 다시 개봉하는 영화와 감독 이야기", 100)
        self.assertEqual(classify_topics(candidate)[0], "film_cinema")

    def test_distressing_news_is_penalized(self) -> None:
        candidate = post("D", "회장이 경기 도중 사망한 사건", 100)
        multiplier, reasons = risk_multiplier(candidate)
        self.assertLess(multiplier, 0.5)
        self.assertIn("death", reasons)

    def test_reuse_restriction_is_effectively_excluded(self) -> None:
        candidate = post("R", "Copyright SBS. 무단 전재, 재배포 및 AI학습 이용 금지", 100)
        multiplier, reasons = risk_multiplier(candidate)

        self.assertLess(multiplier, 0.1)
        self.assertIn("reuse_restricted", reasons)

    def test_thin_streaming_promo_is_penalized_but_animal_clip_is_not(self) -> None:
        promo = post("P", "새 드라마 8월 공개. 오직 넷플릭스에서.", 100, owner="netflixkr")
        animal = post("A", "A rescued baby seal sees snow", 100, owner="sealrescueireland")

        self.assertLess(editorial_multiplier(promo, "series_entertainment"), 0.5)
        self.assertEqual(editorial_multiplier(animal, "animal_cute"), 1.0)


class LearningTests(unittest.TestCase):
    def test_profile_learns_animal_outperformance(self) -> None:
        posts = [
            post("A1", "귀여운 아기 물범", 900),
            post("A2", "판다 가족의 다정한 일상", 700),
            post("F1", "새 영화 개봉 소식", 100),
            post("F2", "극장 시사회와 감독", 90),
            post("G1", "일상 이야기", 100),
            post("G2", "생활 속 작은 이유", 110),
        ]
        profile = build_life_profile(posts, NOW)

        self.assertGreater(
            profile["category_factors"]["animal_cute"],
            profile["category_factors"]["film_cinema"],
        )
        self.assertEqual(profile["sample_count"], 6)

    def test_credit_accounts_become_learned_sources(self) -> None:
        winner = post("W", "귀여운 아기 물범\n\n📸 @seal.rescue", 900)
        loser = post("L", "영화 개봉 소식\n\n📸 @movie.weak", 50)
        profile = build_life_profile([winner, loser], NOW)

        handles = [row["handle"] for row in profile["learned_sources"]]
        self.assertIn("seal.rescue", handles)
        self.assertNotIn("artart.life", extract_source_handles(winner))


class CandidateTests(unittest.TestCase):
    def test_today_requires_mature_high_performing_carousel(self) -> None:
        life_posts = [post("L1", "새 영화 개봉", 100)]
        today_posts = [
            post("T1", "판다 가족의 귀여운 하루", 800, owner="artart.today", age_hours=60),
            post("T2", "그냥 평범한 소식", 100, owner="artart.today", age_hours=60),
            post("T3", "수달 영상", 200, owner="artart.today", age_hours=60, post_type="Video"),
            post("T4", "아직 덜 익은 고양이", 1000, owner="artart.today", age_hours=12),
        ]
        profile = build_life_profile(life_posts, NOW)
        selected = collect_today_candidates(
            today_posts, life_posts, profile, {"sent": {}}, NOW
        )

        self.assertEqual([row["shortCode"] for row in selected], ["T1"])

    def test_recent_life_topic_blocks_duplicate_today_followup(self) -> None:
        life_posts = [post("L1", "바오 판다 가족의 아기 이름", 100)]
        today_posts = [
            post("T1", "바오 판다 가족의 아기 이름 공모", 1000, owner="artart.today")
        ]
        profile = build_life_profile(life_posts, NOW)

        selected = collect_today_candidates(
            today_posts, life_posts, profile, {"sent": {}}, NOW
        )
        self.assertEqual(selected, [])

    def test_balanced_selection_contains_both_routes(self) -> None:
        def candidate(code: str, route: str, category: str, score: float) -> dict:
            return {
                "shortCode": code,
                "_route": route,
                "_category": category,
                "_radar_score": score,
                "_tokens": {code, category},
            }

        today = [candidate("T1", "today_followup", "animal_cute", 4.0)]
        external = [
            candidate("E1", "external_discovery", "anime_character", 3.0),
            candidate("E2", "external_discovery", "human_emotion", 2.0),
        ]
        selected = select_balanced(today, external, 3)

        self.assertEqual(len(selected), 3)
        self.assertEqual({row["_route"] for row in selected}, {
            "today_followup", "external_discovery"
        })

    def test_balanced_selection_does_not_repeat_one_source_account(self) -> None:
        def candidate(code: str, owner: str, score: float, category: str) -> dict:
            return {
                "shortCode": code,
                "owner": owner,
                "_route": "external_discovery",
                "_category": category,
                "_radar_score": score,
                "_tokens": {code, owner},
            }

        external = [
            candidate("E1", "netflixkr", 5.0, "human_emotion"),
            candidate("E2", "netflixkr", 4.0, "anime_character"),
            candidate("E3", "thedodo", 3.0, "animal_cute"),
        ]
        selected = select_balanced([], external, 3)

        self.assertEqual([row["shortCode"] for row in selected], ["E1", "E3"])

    def test_similarity_needs_two_shared_meaningful_tokens(self) -> None:
        self.assertEqual(token_similarity({"판다", "가족"}, {"판다", "이름"}), 0.0)
        self.assertGreater(
            token_similarity({"판다", "가족", "아기"}, {"판다", "가족", "이름"}),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
