# artart-ig-monitor

외부 인스타그램 계정의 시의성 게시물을 Apify로 스크랩 → ARTART 톤 필터·스코어링 → Slack 발송하는 모니터링 스크립트.

순수 Python 표준 라이브러리(stdlib)만 사용 — `pip install` 불필요.

## 실행
```
APIFY_TOKEN=... SLACK_WEBHOOK_URL=...        python3 -m src.monitor.trending_slack --slot morning --top 3              # 투데이 프로필
APIFY_TOKEN=... SLACK_STORICA_WEBHOOK_URL=... python3 -m src.monitor.trending_slack --profile storica --slot morning   # 스토리카(계정별 TOP 2)
```

## ARTART LIFE 자동 소재 레이더

매일 09:10 KST에 GitHub Actions에서 실행한다.

- `@artart.life` 최근 성과를 다시 학습해 동물·애니·감정 서사·영화 등 주제별 가중치를 갱신한다.
- `@artart.today`에서 최소 36시간 지난 고성과 캐러셀 중 LIFE 후속으로 적합한 소재를 찾는다.
- LIFE에서 잘된 게시물의 출처 계정을 자동 학습해 고정 영화 계정 밖의 새 소재도 찾는다.
- 최근 LIFE 게시물과 지난 추천을 대조해 같은 주제를 다시 보내지 않는다.
- 인스타 자동 발행은 하지 않고 `#01_라이프_소재공유`에 최대 3개만 보낸다.

```bash
APIFY_TOKEN=... SLACK_LIFE_WEBHOOK_URL=... \
  python3 -m src.monitor.life_radar --no-send
```

토큰/웹훅은 환경변수로만 주입하며, 이 레포에는 일절 포함하지 않는다.
