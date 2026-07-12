# -*- coding: utf-8 -*-
"""인스타그램 그래프 API 공통 모듈 (표준 라이브러리만 사용)."""
import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# IG_CONFIG 환경변수로 다른 계정 설정 파일을 지정할 수 있다 (예: 에이밍 자동발행).
# 미지정 시 기존 @artart.today 설정 그대로.
CONFIG_PATH = Path(os.environ.get("IG_CONFIG") or (PROJECT_ROOT / "config" / "instagram.json"))

API_VERSION = "v23.0"
TEMP_REPO = "munsok91/artart-ig-temp"
RAW_BASE = f"https://raw.githubusercontent.com/{TEMP_REPO}/main"


class IgError(Exception):
    pass


def load_config():
    if not CONFIG_PATH.exists():
        raise IgError(
            "인스타 계정 연결이 아직 안 됐어요.\n"
            "프로젝트 폴더의 '인스타 계정 연결.command'를 먼저 실행해 주세요."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    CONFIG_PATH.chmod(0o600)


def api_get(cfg, path, params=None):
    params = dict(params or {})
    params["access_token"] = cfg["access_token"]
    url = f"https://{cfg['host']}/{API_VERSION}/{path}?" + urllib.parse.urlencode(params)
    return _request(url)


def api_post(cfg, path, params=None):
    params = dict(params or {})
    params["access_token"] = cfg["access_token"]
    url = f"https://{cfg['host']}/{API_VERSION}/{path}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    return _request(url, data=data)


def _request(url, data=None):
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except Exception:
            msg = body
        raise IgError(f"인스타 서버 응답 오류: {msg}") from None


def refresh_token_if_needed(cfg):
    """인스타 로그인 토큰은 60일짜리 — 7일 넘게 지났으면 자동으로 새 걸로 갱신."""
    if cfg.get("host") != "graph.instagram.com":
        return cfg
    age_days = (time.time() - cfg.get("refreshed_at", 0)) / 86400
    if age_days < 7:
        return cfg
    try:
        url = ("https://graph.instagram.com/refresh_access_token?"
               + urllib.parse.urlencode({
                   "grant_type": "ig_refresh_token",
                   "access_token": cfg["access_token"],
               }))
        res = _request(url)
        cfg["access_token"] = res["access_token"]
        cfg["refreshed_at"] = time.time()
        save_config(cfg)
        print("🔑 접속 열쇠(토큰)를 새 걸로 갱신했어요. (60일 연장)")
    except Exception as e:
        print(f"⚠️ 토큰 갱신은 건너뜁니다 ({e}) — 발행은 계속 진행해요.")
    return cfg


# ---------- 깃허브 임시 이미지 호스팅 ----------

def _gh(args, input_json=None):
    cmd = ["gh", "api"] + args
    kwargs = {"capture_output": True, "text": True}
    if input_json is not None:
        cmd += ["--input", "-"]
        kwargs["input"] = json.dumps(input_json)
    r = subprocess.run(cmd, **kwargs)
    if r.returncode != 0:
        raise IgError(f"깃허브 업로드 오류: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def upload_temp_image(local_path, remote_path):
    """이미지를 임시 저장소에 올리고 (공개주소, 삭제용 sha)를 반환."""
    content = base64.b64encode(Path(local_path).read_bytes()).decode("ascii")
    res = _gh(
        ["-X", "PUT", f"repos/{TEMP_REPO}/contents/{remote_path}"],
        input_json={"message": f"temp {remote_path}", "content": content},
    )
    sha = res["content"]["sha"]
    return f"{RAW_BASE}/{urllib.parse.quote(remote_path)}", sha


def delete_temp_image(remote_path, sha):
    try:
        _gh(
            ["-X", "DELETE", f"repos/{TEMP_REPO}/contents/{remote_path}"],
            input_json={"message": f"cleanup {remote_path}", "sha": sha},
        )
    except Exception:
        pass  # 청소 실패는 발행 성공에 영향 없음


# ---------- 캐러셀 발행 ----------

def wait_container(cfg, container_id, label=""):
    for _ in range(60):
        res = api_get(cfg, container_id, {"fields": "status_code"})
        code = res.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise IgError(f"{label} 처리 중 오류가 났어요. (인스타 쪽 이미지 검사 실패)")
        time.sleep(3)
    raise IgError(f"{label} 처리가 너무 오래 걸려요. 잠시 후 다시 시도해 주세요.")


def publish_carousel(cfg, image_urls, caption, on_progress=print):
    ig_user = cfg["ig_user_id"]
    children = []
    for i, url in enumerate(image_urls, 1):
        on_progress(f"  · 슬라이드 {i}/{len(image_urls)} 등록 중...")
        res = api_post(cfg, f"{ig_user}/media", {"image_url": url, "is_carousel_item": "true"})
        children.append(res["id"])
    for i, cid in enumerate(children, 1):
        wait_container(cfg, cid, f"슬라이드 {i}")
    on_progress("  · 캐러셀 묶는 중...")
    res = api_post(cfg, f"{ig_user}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
    })
    carousel_id = res["id"]
    wait_container(cfg, carousel_id, "캐러셀")
    on_progress("  · 발행 중...")
    res = api_post(cfg, f"{ig_user}/media_publish", {"creation_id": carousel_id})
    media_id = res["id"]
    try:
        link = api_get(cfg, media_id, {"fields": "permalink"}).get("permalink", "")
    except Exception:
        link = ""
    return media_id, link
