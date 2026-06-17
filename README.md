# artart-ig-monitor

외부 인스타그램 계정의 시의성 게시물을 Apify로 스크랩 → ARTART 톤 필터·스코어링 → Slack 발송하는 모니터링 스크립트.

순수 Python 표준 라이브러리(stdlib)만 사용 — `pip install` 불필요.

## 실행
```
APIFY_TOKEN=... SLACK_WEBHOOK_URL=...        python3 -m src.monitor.trending_slack --slot morning --top 3              # 투데이 프로필
APIFY_TOKEN=... SLACK_STORICA_WEBHOOK_URL=... python3 -m src.monitor.trending_slack --profile storica --slot morning   # 스토리카(계정별 TOP 2)
```

토큰/웹훅은 환경변수로만 주입하며, 이 레포에는 일절 포함하지 않는다.
