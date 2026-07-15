#!/usr/bin/env python3
"""경제 소재공유방(02_경제채널_운영) 사용 소재 체크 표시.

슬랙 메시지는 웹후크(봇)로 올라가 원문 편집이 불가능하다.
대신 ① 부모 메시지에 ✅ 리액션 ② 스레드 답글로 "몇 번 항목을 어느 채널이 썼는지" 를 남긴다.

사용법:
  python3 mark_used.py --topic "코스피 서킷브레이커" --used-by "머니먼데이 ep10"
  python3 mark_used.py --topic "서울 2030 부모 증여" --used-by "에이밍 ep05" --days 7

--topic 은 소재를 식별할 키워드(공백 구분). 최근 --days 일치 메시지에서 제목이 가장 잘 맞는
항목을 찾아 표시한다. 이미 표시한 항목은 .used_marks.json 으로 걸러 중복 표시하지 않는다.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

CHANNEL = "C068V12RURE"  # 02_경제채널_운영
STATE = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "econ", ".used_marks.json")
NUM_EMOJI = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "keycap_ten": 10,
}


def api(method, token, post=False, **params):
    url = "https://slack.com/api/" + method
    headers = {"Authorization": "Bearer " + token}
    if post:
        headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=json.dumps(params).encode(), headers=headers, method="POST")
    else:
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=25))


def post_webhook(text, thread_ts):
    """발송용 웹후크로 스레드 답글을 단다 (읽기 전용 토큰으로는 chat.postMessage 불가)."""
    hook = os.environ.get("SLACK_ECON_WEBHOOK_URL")
    if not hook:
        sys.exit("SLACK_ECON_WEBHOOK_URL 없음 — .env 를 source 하고 실행하세요.")
    data = json.dumps({"text": text, "thread_ts": thread_ts, "unfurl_links": False}).encode()
    req = urllib.request.Request(hook, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=25).read().decode() == "ok"


def parse_items(text):
    """메시지 본문에서 (번호, 제목, URL) 목록을 뽑는다.

    10번 이상은 :one::one: (11), :one::two: (12) 처럼 숫자 이모지 2개를 이어 붙여 쓴다.
    """
    items, lines = [], text.split("\n")
    for i, ln in enumerate(lines):
        m = re.match(r"((?::\w+:)+)\s*\*{0,2}(.+?)\*{0,2}\s*$", ln.strip())
        if not m:
            continue
        names = re.findall(r":(\w+):", m.group(1))
        if not names or not all(n in NUM_EMOJI for n in names) or len(names) > 2:
            continue
        num = NUM_EMOJI[names[0]] if len(names) == 1 else NUM_EMOJI[names[0]] * 10 + NUM_EMOJI[names[1]]
        url = ""
        for nxt in lines[i + 1:i + 4]:
            u = re.search(r"<(https?://[^>|]+)>", nxt)
            if u:
                url = u.group(1)
                break
        items.append({"n": num, "title": m.group(2).strip(), "url": url})
    return items


def score(title, keywords):
    t = title.replace(" ", "")
    return sum(1 for k in keywords if k.replace(" ", "") in t)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"marks": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="소재 식별 키워드 (공백 구분)")
    ap.add_argument("--used-by", required=True, help="사용 채널·회차 (예: '머니먼데이 ep10')")
    ap.add_argument("--url", default="", help="원 소재 URL (있으면 우선 매칭)")
    ap.add_argument("--days", type=int, default=7, help="며칠치 메시지에서 찾을지")
    ap.add_argument("--all", action="store_true", help="같은 소재가 여러 날 올라왔으면 전부 표시 (기본: 최신 1건)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        sys.exit("SLACK_USER_TOKEN 없음 — .env 를 source 하고 실행하세요.")

    keywords = args.topic.split()
    oldest = (datetime.datetime.now() - datetime.timedelta(days=args.days)).timestamp()
    hist = api("conversations.history", token, channel=CHANNEL, limit=100, oldest=int(oldest))
    if not hist.get("ok"):
        sys.exit(f"슬랙 조회 실패: {hist.get('error')}")

    state = load_state()
    done = {(m["ts"], m["n"]) for m in state["marks"]}

    hits = []  # (점수, ts, item)
    for msg in hist["messages"]:
        for item in parse_items(msg.get("text", "")):
            if (msg["ts"], item["n"]) in done:
                continue
            s = 100 if (args.url and args.url == item["url"]) else score(item["title"], keywords)
            if s >= max(2, len(keywords) - 1) or s >= 100:
                hits.append((s, msg["ts"], item))

    if not hits:
        print(f"[mark] 매칭되는 소재 없음 (topic={args.topic}) — 표시 건너뜀")
        return

    # 같은 소재가 여러 날 올라왔으면 기본은 가장 최근 메시지 1건만 표시한다.
    targets = sorted(hits, key=lambda x: -x[0]) if args.all else [max(hits, key=lambda x: (float(x[1]), x[0]))]

    for s, ts, item in targets:
        line = f":white_check_mark: *사용 완료* — {item['n']}️⃣ {item['title']}\n→ {args.used_by} 로 제작됨"
        if args.dry_run:
            print(f"[dry-run] ts={ts} n={item['n']} score={s} :: {item['title'][:40]} → {args.used_by}")
            continue
        # SLACK_USER_TOKEN 은 읽기 전용(channels:history)이라 chat.write/reactions.add 불가.
        # 발송과 같은 웹후크로 부모 메시지의 스레드에 답글을 단다.
        if not post_webhook(line, ts):
            print(f"[warn] 답글 실패 ts={ts}")
            continue
        state["marks"].append({"ts": ts, "n": item["n"], "title": item["title"], "used_by": args.used_by})
        print(f"[mark] ✅ {item['n']}️⃣ {item['title'][:40]} → {args.used_by}")

    if not args.dry_run:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        state["marks"] = state["marks"][-300:]
        with open(STATE, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
