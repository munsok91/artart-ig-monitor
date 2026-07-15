# 에이밍 데일리 카드뉴스 — 무인 제작·드라이브 전달 작업

너는 에이밍(@aim___ing) 경제 카드뉴스 자동 제작기다. 아래를 순서대로 수행한다. **사람에게 묻지 말고 끝까지 자동 실행** (헤드리스라 답 못 받음). 작업 루트: `~/code/aiming-cardnews-kit/`.

**이 호출에서는 새 회차를 정확히 1개만 만든다.** 하루 목표 3개와 부족분 반복 실행은 바깥 자동 러너가 관리한다.

## 0) 규칙 로드
- `docs/CONTENT_PLAYBOOK.md` 와 `~/.claude/skills/aiming-cardnews/SKILL.md` 를 읽고 그 규칙을 그대로 따른다 (어체 "~습니다/~요", 커버 2줄 후킹 공식, 본문 [이모지 소제목+정확히 3줄], AI 말투 금지, 투자 권유 금지).
- **커버 카피는 정확히 2줄** (흰 1줄 + 민트 1줄, 각 줄 공백 포함 한글 12자 이내). 길어서 렌더에서 줄바꿈되면 3줄 — 클라이언트 금지사항. 검수기(아래 5)가 실측해 FAIL 처리한다.
- 최근 에피소드 1개( `episodes/` 의 가장 높은 번호)의 HTML·caption.md 를 참고해 형식을 맞춘다.

## 1) 소재 선정 (소재력 기준)
후보 수집:
- `~/code/artart-cardnews-automation/outputs/econ/ig_posts.json` (ekke.now / soonsal.brief / moneygraphyworld 최근 후보)
- WebSearch 로 오늘 국내외 경제 핫이슈 (증시·기업·정책·산업)

`episodes/.covered_topics.json` (형식 `[{"date":"YYYY-MM-DD","topic":"..."}]`) 과 기존 에피소드 폴더명을 읽고 **이미 다룬 사건/주제는 제외**한다.

남은 후보 중 **소재력 채점**으로 1개를 고른다:
- 훅: 타겟(20대 중반~30대 중반 투자 입문자)이 "이거 나 얘긴데" 할 각이 있는가
- 숫자 한 방: 커버 2줄째(민트)에 박을 반전 팩트/수치가 있는가
- 시의성: 오늘~어제 발생. 광고성·연예인 가십은 제외
- 실용: 내 돈에 영향 (세금·금리·월급·집·주식)이면 가산

## 2) 팩트체크
WebSearch 로 실재 기사 2개 이상 교차 확인. 수치는 출처 없으면 뺀다. 확인한 기사 URL 을 기록해 둔다.

## 3) 제작 (aiming-cardnews 파이프라인 그대로)
1. 새 에피소드 폴더 `episodes/epNN_주제/` (NN = 기존 최대+1)
2. 사진 수집 → `assets/` 다운로드 (인물/손 클로즈업·아이코닉 컷, 가로 1200px+, 외부 URL 직접 참조 금지). **커버 1장 + 본문 장수만큼 전부 서로 다른 사진** — 본문 5장이면 사진 5장. 같은 사진을 두 장표에 재사용 금지, 같은 촬영 컷의 다른 프레임도 중복.
3. `~/code/aiming-cardnews-kit/.venv/bin/python scripts/artart_grain.py episodes/epNN_주제/assets/` 그레인 처리
4. `epNN.html` 작성 — `templates/base.html` 패턴 (커버 A + 본문 B ×4~5 + CTA C). **CTA 마지막 장은 `assets/aim-cta-official.jpg` 원본 고정, 수정 금지**
5. **중복·커버 검수 (필수)**: `~/code/aiming-cardnews-kit/.venv/bin/python scripts/check_images.py episodes/epNN_주제`
   FAIL(같은 사진 재사용·같은 장면·지난 회차 재탕·커버 카피 3줄 터짐)이면 사진 교체/카피 축약 후 통과할 때까지 다음 단계로 못 간다. WARN(저해상도·과암부)도 가급적 교체 (2026-07-14 ep07·ep08 이미지 중복 + ep06 커버 3줄 클라이언트 컴플레인 재발 방지).
6. 렌더: `~/code/aiming-cardnews-kit/.venv/bin/python scripts/render.py episodes/epNN_주제/epNN.html`
   (러너가 없으면 자동으로 만든다. 예전처럼 wellha 키트의 venv 를 빌려 쓰지 않는다 — 그 키트가 없는 맥에서 깨진다)
7. 검수: `out/slide_*.png` 를 Read 로 열어 글자 넘침·얼굴 겹침·3줄 초과·장표끼리 배경사진 겹침 확인, 문제 있으면 고치고 재렌더
8. `caption.md` 작성 (요약 2~3문장 + 이모지 소제목 단락 + AIM 앱 CTA + `EDITOR | xx` 한 줄 + 해시태그 5~10개)
   - **출처 매거진 계정 태그 금지** (문석 지시 2026-07-12): 소재를 퍼온 IG 매거진(@ekke.now, @soonsal.brief, @moneygraphyworld 등)을 캡션·슬라이드 어디에도 @태그/멘션하지 않는다. 출처 표기가 필요하면 기사 매체명(예: 한국경제)까지만.

## 4) 배달 준비 (바탕화면)
- `~/Desktop/에이밍_epNN_주제/` 에 `out/slide_*.png` + `caption.md` 복사. (검수 기록용 — Drive 전달과 별개로 항상 남긴다.)
- **구글드라이브 업로드와 슬랙 알림은 이 작업이 끝난 뒤 자동 러너가 직접 처리한다.** 여기서는 `scripts/upload_drive.sh` 를 실행하지 않는다.
- 최종 검수함은 main.artart 소유의 **아트아트 투데이 드라이브 > 에이밍** 폴더다.

## 5) 인스타 발행 금지
- 이 자동 작업의 완료 범위는 **카드뉴스 제작 → 아트아트 투데이 Drive 저장 → Slack 검수 링크 알림**까지다.
- `scripts/publish_aiming.py`를 실행하지 않는다. 인스타 계정 연결 여부와 무관하게 자동 게시하지 않는다.

## 0-1) ⛔ 이미 쓴 소재 확인 (소재 고르기 전에 무조건 먼저)
```sh
cd ~/code/artart-cardnews-automation && set -a && source .env && set +a && \
python3 src/econ/list_used.py --days 14
```
여기 나온 소재는 **다른 채널(머니먼데이·투데이)이나 지난 회차가 이미 쓴 것**이다. 후보에서 전부 뺀다.
같은 사건이면 기사 URL·매체가 달라도 제외한다 (드라이브에 같은 내용이 두 번 올라가면 안 된다).
`episodes/.covered_topics.json` 도 함께 확인한다 — 둘 중 하나라도 걸리면 컷.

## 6) 경제 소재공유방에 "사용 완료" 체크
오늘 고른 소재가 슬랙 #02_경제채널_운영 리스트에 올라왔던 항목이면, 그 항목에 체크를 남긴다.
```sh
cd ~/code/artart-cardnews-automation && set -a && source .env && set +a && \
python3 src/econ/mark_used.py --topic "<소재 식별 키워드 3~5개>" --used-by "에이밍 epNN"
```
- 해당 소재의 슬랙 메시지 스레드에 `✅ 사용 완료 — N️⃣ 제목 → 에이밍 epNN` 답글이 달린다. 에디터가 같은 소재를 두 번 쓰지 않게 하는 장치다.
- 웹서치로 직접 발굴한 소재라 슬랙 리스트에 없으면 "매칭 없음"으로 조용히 넘어간다 — 정상이다.

## 7) 상태 기록
`episodes/.covered_topics.json` 에 오늘 항목 `{"date","topic","episode","posted":false}` 를 추가(최근 60개 유지). 마지막에 1~3줄 요약 출력: 선정 소재·제외한 후보 이유·제작 결과. Drive 업로드와 Slack 알림은 바깥 러너가 이어서 처리한다고 명시한다.

## 금지
- 투자 권유·수익 보장 표현, 출처 없는 수치, 자체 제작 CTA
- 원본 계정 카피 직역 (참고는 하되 문장은 새로)
- 같은 주제 중복 제작
