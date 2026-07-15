# -*- coding: utf-8 -*-
"""이미 다른 채널이 쓴 소재 목록 (경제 소재공유방 ✅ 사용 완료 스레드 기준).

소재 선정 전에 이걸 먼저 읽고, 여기 있는 소재는 후보에서 뺀다.
채널이 여러 개(에이밍·머니먼데이·투데이)라 같은 소재를 두 번 만들어 드라이브에
중복 업로드되는 사고를 막는 장치다.

진실의 원천은 슬랙 스레드다 (맥이 여러 대라 로컬 파일만으로는 못 맞춘다).
로컬 `.used_marks.json` 은 보조 캐시로만 합친다.

사용법:
  python3 src/econ/list_used.py            # 최근 14일치, 사람이 읽는 목록
  python3 src/econ/list_used.py --json     # 기계용 JSON
  python3 src/econ/list_used.py --days 30
"""
import argparse
import datetime
import json
import os
import re
import sys

from mark_used import CHANNEL, api, load_state, parse_items


def fetch_used(token, days):
    """부모 메시지의 항목 중, 스레드에 '✅ 사용 완료' 답글이 달린 것을 모은다."""
    oldest = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()
    hist = api("conversations.history", token, channel=CHANNEL, limit=200, oldest=int(oldest))
    if not hist.get("ok"):
        sys.exit(f"슬랙 조회 실패: {hist.get('error')}")

    used = []
    for msg in hist["messages"]:
        if not msg.get("reply_count"):
            continue
        rep = api("conversations.replies", token, channel=CHANNEL, ts=msg["ts"], limit=50)
        for r in rep.get("messages", [])[1:]:
            t = r.get("text", "")
            if "사용 완료" not in t and ":white_check_mark:" not in t:
                continue
            # 제목은 답글 본문에서 직접 읽는다 (부모 메시지 번호로 되짚으면 어긋난다 —
            # 10번 이상은 :one::two: 처럼 이모지 2개라 숫자 파싱이 틀린다)
            head = t.split("\n")[0]
            head = re.sub(r"^.*?—\s*", "", head)              # "✅ *사용 완료* — " 제거
            title = re.sub(r"^(?::\w+:|\d|️|⃣|\s)+", "", head).strip("* ")
            by = ""
            mb = re.search(r"→\s*(.+?)(?:\s*로 제작됨)?\s*$", t.split("\n")[-1])
            if mb:
                by = mb.group(1).strip()
            used.append({"title": title, "used_by": by, "ts": msg["ts"]})
    return used


def dedupe(rows):
    """같은 소재가 여러 경로(슬랙 답글 + 로컬 캐시)로 들어오므로 제목 기준으로 합친다."""
    out, seen = [], set()
    for r in rows:
        key = re.sub(r"\s+", "", r["title"])[:24]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        sys.exit("SLACK_USER_TOKEN 없음 — .env 를 source 하고 실행하세요.")

    used = fetch_used(token, args.days)

    # 로컬 캐시도 합친다 (슬랙 조회 실패·표시 누락 대비). 이 맥에만 있는 기록일 수 있다.
    for m in load_state()["marks"]:
        used.append({"title": m["title"], "used_by": m.get("used_by", ""), "ts": m["ts"]})
    used = dedupe(used)

    if args.json:
        print(json.dumps(used, ensure_ascii=False, indent=1))
        return

    if not used:
        print("(최근 사용 기록 없음 — 전부 후보)")
        return
    print(f"이미 쓴 소재 {len(used)}건 — 아래 주제는 후보에서 제외한다:")
    for u in used:
        print(f"  · {u['title']}   → {u['used_by']}")


if __name__ == "__main__":
    main()
