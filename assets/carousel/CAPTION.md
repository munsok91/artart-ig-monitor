# 캐러셀 · "Claude & Fable 신상 AI 등장" 밈

소재 사진: 트럼프가 `Claude`·`Fable` 자루 두 개를 메고 나오는 밈
톤: 한국어 밈 반말 · 정보성 살짝

## 업로드용 캡션 (복붙용)

```
요즘 개발자·기획자들 이거 두 개 메고 다닌다는데 ㅋㅋㅋ 💼💼

새로 풀린 AI 모델 둘 —
🧠 Claude : 길게 생각·복잡한 작업은 얘한테
✨ Fable : 급할 때 빠르게 쳐내는 건 얘가 답

뭐 쓸지 고민되면? 트럼프처럼 그냥 둘 다 메고 다니면 됨 ㅋ

남들 아직 모를 때 저장 📌 해두고 먼저 챙기자.
AI 시의성 소식은 @artart 에서 계속 ✌️

.
.
#AI #클로드 #Claude #Fable #인공지능 #AI모델 #생성형AI #챗봇
#개발자 #기획자 #AI툴 #밈 #직장인밈 #IT #테크 #artart
```

## 슬라이드 구성 (6장)

| # | 파일 | 내용 |
|---|------|------|
| 1 | `01.png` | (밈 사진) "요즘 개발자·기획자 근황.jpg" — 둘 다 들고 다닌다는 신상 AI 두 개 |
| 2 | `02.png` | 등장인물 정리 — 왼쪽 Claude / 오른쪽 Fable |
| 3 | `03.png` | 1번 자루 · Claude 🧠 — "길게 생각하는 건 얘한테 시켜" |
| 4 | `04.png` | 2번 자루 · Fable ✨ — "급할 땐 얘가 답이야" |
| 5 | `05.png` | TL;DR 비교 — 깊게=Claude / 빠르게=Fable / 고민되면 둘 다 |
| 6 | `06.png` | 마무리 CTA — 저장·공유 + @artart |

## 다시 생성하기

```
python3 build/gen_slides.py
```

- 결과물: `assets/carousel/01.png` ~ `06.png` (1080×1080)
- 원본 밈 사진: `assets/carousel/00_source_trump_bags.png`
- 렌더링: 헤드리스 Chromium 스크린샷 (시스템 CJK 폰트 사용, 외부 네트워크 불필요)
- 문구·색상은 `build/gen_slides.py` 상단 상수/슬라이드 HTML에서 수정
