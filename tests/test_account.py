"""로그인 상태 파일 읽기·서버 요청 (Step 4-2) — 실제 서버 대신 가짜 전송으로 검사."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from account import Session, current_session, rest  # noqa: E402

GOOD = {"url": "https://x.supabase.co", "key": "sb_publishable_test", "user_id": "u1", "email": "a@b.c",
        "access_token": "tok", "expires_at": 2_000}


def test_reads_session_file(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps(GOOD))
    assert current_session(f, now=1_000) == Session(**GOOD)
    assert current_session(f, now=2_000) is None          # 만료
    f.write_text("{}")                                     # 로그아웃 상태
    assert current_session(f, now=1_000) is None
    f.write_text("깨진 파일")
    assert current_session(f, now=1_000) is None
    assert current_session(tmp_path / "없음.json") is None  # 로컬 실행


def test_rest_sends_user_token_and_parses():
    sent = []

    def fake(method, url, headers, body):
        sent.append((method, url, headers, body))
        return 200, '[{"user_id": "u1"}]'

    s = Session(**GOOD)
    assert rest(s, "POST", "intakes", {"mg": 75}, transport=fake) == [{"user_id": "u1"}]
    method, url, headers, body = sent[0]
    assert (method, url) == ("POST", "https://x.supabase.co/rest/v1/intakes")
    assert headers["Authorization"] == "Bearer tok" and headers["apikey"] == "sb_publishable_test"
    assert json.loads(body) == {"mg": 75}


def test_rest_raises_on_error():
    with pytest.raises(RuntimeError, match="401"):
        rest(Session(**GOOD), "GET", "profiles", transport=lambda *a: (401, '{"message":"JWT expired"}'))


def test_index_html_and_python_agree_on_session_file():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    import account
    assert f'SESSION_FILE = "{account.SESSION_FILE.name}"' in html
