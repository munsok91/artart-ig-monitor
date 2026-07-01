#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
캐러셀 슬라이드 생성기 (밈 톤 · 한국어)
- 소재: 트럼프가 "Claude"·"Fable" 자루 두 개를 메고 나오는 밈
- 주제: 새 AI 모델 Claude & Fable 등장 밈 카러셀
- 산출물: assets/carousel/NN.png (1080x1080) 6장

렌더링: 헤드리스 Chromium 스크린샷. 외부 폰트/네트워크 불필요(시스템 CJK 폰트 사용).
실행: python3 build/gen_slides.py
"""
import base64
import os
import subprocess
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets", "carousel")
BUILD = os.path.join(ROOT, "build")
os.makedirs(ASSETS, exist_ok=True)
os.makedirs(BUILD, exist_ok=True)

# 브랜드 팔레트
BG = "#0e0e12"        # 딥 차콜
CARD = "#15151c"
ACCENT = "#FFE14D"    # 밈 옐로우
ACCENT2 = "#7CE7FF"   # 시안
INK = "#f5f5f7"
SUB = "#a0a0ab"
FONT = "'WenQuanYi Zen Hei','Noto Sans CJK KR',sans-serif"

# 소스 사진 base64 임베드
with open(os.path.join(ASSETS, "00_source_trump_bags.png"), "rb") as f:
    PHOTO_B64 = base64.b64encode(f.read()).decode()

BASE_CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ width:1080px; height:1080px; overflow:hidden; }}
body {{ font-family:{FONT}; background:{BG}; color:{INK};
  -webkit-font-smoothing:antialiased; }}
.slide {{ position:relative; width:1080px; height:1080px; overflow:hidden; }}
.pad {{ position:absolute; inset:0; padding:90px 84px; display:flex;
  flex-direction:column; }}
.kicker {{ display:inline-block; font-weight:800; font-size:30px;
  letter-spacing:2px; color:{BG}; background:{ACCENT}; padding:10px 22px;
  border-radius:999px; align-self:flex-start; }}
.big {{ font-weight:900; line-height:1.12; letter-spacing:-1px; }}
.accent {{ color:{ACCENT}; }}
.cyan {{ color:{ACCENT2}; }}
.sub {{ color:{SUB}; }}
.footer {{ margin-top:auto; padding-top:24px; align-self:stretch; width:100%;
  display:flex; justify-content:space-between; align-items:center;
  font-size:26px; line-height:1; color:{SUB}; font-weight:700; }}
.dot {{ display:flex; gap:10px; }}
.dot i {{ width:12px; height:12px; border-radius:99px; background:#33333d;
  display:inline-block; }}
.dot i.on {{ background:{ACCENT}; }}
.tag {{ font-weight:900; color:{ACCENT}; }}
"""

def dots(n, total=6):
    return '<div class="dot">' + "".join(
        f'<i class="{"on" if i==n else ""}"></i>' for i in range(1, total+1)
    ) + "</div>"

def footer(n):
    return f'<div class="footer"><span class="tag">@artart</span>{dots(n)}</div>'

def page(inner, extra_css=""):
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>{BASE_CSS}{extra_css}</style></head><body>{inner}</body></html>"""

# ---------------------------------------------------------------- SLIDE 1
# 밈 사진 풀블리드 + 위/아래 스크림 + 임팩트 자막
slide1 = page(f"""
<div class="slide">
  <img src="data:image/png;base64,{PHOTO_B64}"
    style="position:absolute;inset:0;width:1080px;height:1080px;object-fit:cover;">
  <div style="position:absolute;inset:0;background:
    linear-gradient(180deg,rgba(0,0,0,0) 42%,rgba(0,0,0,.55) 66%,
    rgba(0,0,0,.92) 100%);"></div>
  <div class="topbar">요즘 개발자·기획자 근황.jpg</div>
  <div class="meme meme-bot">둘 다 들고 다닌다는<br>신상 AI 두 개 나왔다는데 ㅋㅋㅋ</div>
</div>
""", extra_css=f"""
.topbar {{ position:absolute; top:0; left:0; right:0; text-align:center;
  color:#fff; font-weight:900; font-size:48px; letter-spacing:-1px;
  padding:34px 40px; background:rgba(0,0,0,.6); }}
.meme {{ position:absolute; left:0; right:0; text-align:center; color:#fff;
  font-weight:900; padding:0 54px; letter-spacing:-1px; line-height:1.16;
  text-shadow:-3px -3px 0 #000,3px -3px 0 #000,-3px 3px 0 #000,3px 3px 0 #000,
    0 4px 0 #000,0 -4px 0 #000,4px 0 0 #000,-4px 0 0 #000,0 8px 24px rgba(0,0,0,.8); }}
.meme-bot {{ bottom:76px; font-size:66px; }}
.meme-bot br + * {{}}
""")

# ---------------------------------------------------------------- SLIDE 2
slide2 = page(f"""
<div class="slide"><div class="pad">
  <span class="kicker">등장인물 정리</span>
  <div style="margin-top:60px" class="big" >
    <div style="font-size:70px">자루 안에 든 게 뭐냐면</div>
  </div>
  <div style="margin-top:64px;display:flex;flex-direction:column;gap:30px">
    <div class="row">
      <div class="lbl">👜 왼쪽</div>
      <div class="val"><b class="accent">Claude</b> · 대장 두뇌형 AI</div>
    </div>
    <div class="row">
      <div class="lbl">👜 오른쪽</div>
      <div class="val"><b class="cyan">Fable</b> · 빠르고 가벼운 신상</div>
    </div>
  </div>
  <div style="margin-top:64px;font-size:40px;line-height:1.4" class="sub">
    둘 다 이번에 새로 풀린<br>최신 세대 AI 모델임.<br>
    <span style="color:#f5f5f7">그래서 다들 하나씩 챙기는 중 ㅇㅇ</span>
  </div>
  {footer(2)}
</div></div>
""", extra_css=f"""
.row {{ display:flex; align-items:center; gap:26px; background:{CARD};
  border:2px solid #23232d; border-radius:26px; padding:30px 34px; }}
.lbl {{ font-size:40px; font-weight:900; min-width:150px; }}
.val {{ font-size:44px; font-weight:800; }}
""")

# ---------------------------------------------------------------- SLIDE 3
slide3 = page(f"""
<div class="slide"><div class="pad">
  <span class="kicker" style="background:{ACCENT}">1번 자루 · Claude 🧠</span>
  <div style="margin-top:56px" class="big">
    <span style="font-size:82px">"길게 생각하는 건<br><span class="accent">얘한테 시켜"</span></span>
  </div>
  <div style="margin-top:56px;font-size:44px;line-height:1.55">
    · 복잡한 코드·긴 문서 <b class="accent">한 방에 정리</b><br>
    · 추론 오래 굴려도 <b class="accent">덜 헛소리</b><br>
    · 일 시키면 <b class="accent">끝까지 물고 늘어짐</b>
  </div>
  <div style="margin-top:56px;font-size:38px" class="sub">
    한줄평: <span style="color:#f5f5f7">"팀에 일 잘하는 사수 하나 꽂은 느낌"</span>
  </div>
  {footer(3)}
</div></div>
""")

# ---------------------------------------------------------------- SLIDE 4
slide4 = page(f"""
<div class="slide"><div class="pad">
  <span class="kicker" style="background:{ACCENT2};color:{BG}">2번 자루 · Fable ✨</span>
  <div style="margin-top:56px" class="big">
    <span style="font-size:82px">"급할 땐<br><span class="cyan">얘가 답이야"</span></span>
  </div>
  <div style="margin-top:56px;font-size:44px;line-height:1.55">
    · 가볍고 <b class="cyan">답 튀어나오는 속도 미쳤음</b><br>
    · 짧은 작업·초안·아이디어 <b class="cyan">순삭</b><br>
    · 부담 없이 <b class="cyan">계속 굴리기 좋음</b>
  </div>
  <div style="margin-top:56px;font-size:38px" class="sub">
    한줄평: <span style="color:#f5f5f7">"손 빠른 막내 인턴인데 일 잘함"</span>
  </div>
  {footer(4)}
</div></div>
""")

# ---------------------------------------------------------------- SLIDE 5
slide5 = page(f"""
<div class="slide"><div class="pad">
  <span class="kicker">그래서 뭐 씀? (TL;DR)</span>
  <div style="margin-top:54px;display:flex;flex-direction:column;gap:24px">
    <div class="cmp"><div class="q">깊게 파야 하는 일</div><div class="a accent">→ Claude</div></div>
    <div class="cmp"><div class="q">빠르게 쳐내는 일</div><div class="a cyan">→ Fable</div></div>
    <div class="cmp"><div class="q">뭐 쓸지 모르겠음</div><div class="a" style="color:#f5f5f7">→ 그냥 둘 다 ㅋㅋ</div></div>
  </div>
  <div style="margin-top:56px;font-size:52px;font-weight:900;line-height:1.3">
    결론:<br><span class="accent">트럼프처럼 두 자루 다 메고 다니면 됨</span> 💼💼
  </div>
  {footer(5)}
</div></div>
""", extra_css=f"""
.cmp {{ display:flex; align-items:center; justify-content:space-between;
  background:{CARD}; border:2px solid #23232d; border-radius:24px;
  padding:30px 36px; }}
.q {{ font-size:44px; font-weight:800; }}
.a {{ font-size:46px; font-weight:900; }}
""")

# ---------------------------------------------------------------- SLIDE 6
slide6 = page(f"""
<div class="slide"><div class="pad" style="justify-content:center;align-items:center;text-align:center">
  <div style="font-size:56px;font-weight:900" class="accent">저장 📌 &nbsp; 공유 ↗</div>
  <div style="margin-top:34px;font-size:76px;font-weight:900;line-height:1.18">
    남들 아직<br>모를 때<br><span class="accent">먼저 챙겨</span>
  </div>
  <div style="margin-top:40px;font-size:40px;line-height:1.5" class="sub">
    AI 시의성 소식은<br><span style="color:#f5f5f7">@artart 에서 계속 ✌️</span>
  </div>
  {footer(6)}
</div></div>
""")

SLIDES = [slide1, slide2, slide3, slide4, slide5, slide6]

# 렌더
chrome = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))[0]
for i, html in enumerate(SLIDES, start=1):
    htmlpath = os.path.join(BUILD, f"slide_{i:02d}.html")
    outpath = os.path.join(ASSETS, f"{i:02d}.png")
    with open(htmlpath, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.run([
        chrome, "--headless=new", "--no-sandbox", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--default-background-color=00000000",
        "--window-size=1080,1080",
        f"--screenshot={outpath}", f"file://{htmlpath}",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"rendered {outpath}")

print("done")
