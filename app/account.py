"""로그인 상태 읽기 + 서버(Supabase) 요청 (Step 4-2).

로그인 자체는 index.html의 자바스크립트(supabase-js)가 맡는다: 메일 링크·코드로 로그인하면 브라우저에
로그인 상태를 저장하고 자동으로 갱신하며, 그 내용을 브라우저 속 Python의 파일(SESSION_FILE)에 써준다.
Python은 이 파일을 읽어 '누가 로그인했는지'와 서버 요청용 열쇠(access_token)를 얻는다.
로컬 실행(streamlit run)에는 이 파일이 없으므로 항상 '로그인 안 됨'.
"""
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SESSION_FILE = ROOT / ".auth_session.json"   # index.html의 SESSION_FILE과 같은 이름
# 공개용 주소·키 (index.html과 같은 값, 누구에게 보여도 되는 키 — 데이터 보호는 RLS가 함).
# 로그인 안 한 사람이 '의견 보내기'처럼 누구나 쓸 수 있는 표에 쓸 때 쓴다.
PUBLIC_URL = "https://arqruewigqgzbmlsgjad.supabase.co"
PUBLIC_KEY = "sb_publishable_d3_p7eyo_DVHwgFvXXMbqw_Z1Pngu2j"

# (method, url, headers, body) → (status, 응답 글)
Transport = Callable[[str, str, Dict[str, str], Optional[str]], Tuple[int, str]]


@dataclass(frozen=True)
class Session:
    url: str            # Supabase 주소
    key: str            # 공개용 키 (누구에게 보여도 되는 키 — 데이터 보호는 RLS가 함)
    user_id: str
    email: str
    access_token: str   # 로그인한 사람만의 열쇠 (1시간마다 자바스크립트가 새로 받아 파일을 다시 씀)
    expires_at: int     # unix 초


def current_session(path: Path = SESSION_FILE, now: Optional[float] = None) -> Optional[Session]:
    """로그인 안 됐거나, 파일이 깨졌거나, 열쇠가 만료됐으면 None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        s = Session(**{k: data[k] for k in Session.__dataclass_fields__})
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return s if s.expires_at > (time.time() if now is None else now) else None


def _send_cpython(method, url, headers, body):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=body.encode() if body is not None else None, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _send_browser(method, url, headers, body):
    from js import XMLHttpRequest  # stlite(Pyodide)에서만 존재 — Web Worker라 동기 요청 가능
    xhr = XMLHttpRequest.new()
    xhr.open(method, url, False)
    for k, v in headers.items():
        xhr.setRequestHeader(k, v)
    xhr.send(body)
    return xhr.status, xhr.responseText


def default_transport() -> Transport:
    return _send_browser if sys.platform == "emscripten" else _send_cpython


def rest(session: Optional[Session], method: str, path: str, body=None, transport: Optional[Transport] = None,
         prefer: Optional[str] = None, returning: bool = True):
    """서버 표 읽기·쓰기 (PostgREST). 예: rest(s, "GET", "profiles?select=*")
    로그인한 사람의 열쇠로 요청하므로 RLS 규칙에 따라 자기 행만 보인다.
    prefer: 추가 요청 방식. 예: "resolution=merge-duplicates" (있으면 고치고 없으면 넣기)
    session=None: 로그인 안 한 사람(anon)으로 요청 — 누구나 쓸 수 있는 표에만 쓸 수 있다.
    returning=False: 넣은 행을 돌려받지 않음 (읽기 규칙이 없는 표에 쓸 때 필요)."""
    url, key = (session.url, session.key) if session else (PUBLIC_URL, PUBLIC_KEY)
    token = session.access_token if session else PUBLIC_KEY
    headers = {"apikey": key, "Authorization": f"Bearer {token}", "Content-Type": "application/json",
               "Prefer": ",".join(filter(None, ["return=representation" if returning else "return=minimal", prefer]))}
    data = json.dumps(body, ensure_ascii=False) if body is not None else None
    status, text = (transport or default_transport())(method, f"{url}/rest/v1/{path}", headers, data)
    if not 200 <= status < 300:
        raise RuntimeError(f"서버 응답 {status}: {text[:300]}")
    return json.loads(text) if text else None
