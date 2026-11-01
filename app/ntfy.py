"""ntfy로 예약 푸시 보내기.

로컬 Python(CPython)은 urllib, 웹(GitHub Pages의 stlite = 브라우저 속 Python)은 urllib이 동작하지
않으므로 브라우저의 XMLHttpRequest를 쓴다. stlite의 Python은 Web Worker에서 돌아서 동기 요청이 허용된다.
"""
import json
import sys
from typing import Callable, Dict, Optional

from caffeine_engine import params
from caffeine_engine.notify import Scheduled

Transport = Callable[[str, bytes], Dict]


def _post_cpython(url: str, body: bytes) -> Dict:
    import urllib.request
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _post_browser(url: str, body: bytes) -> Dict:
    from js import XMLHttpRequest  # stlite(Pyodide)에서만 존재
    xhr = XMLHttpRequest.new()
    xhr.open("POST", url, False)
    xhr.setRequestHeader("Content-Type", "application/json")
    xhr.send(body.decode())
    if not 200 <= xhr.status < 300:
        raise RuntimeError(f"ntfy 응답 {xhr.status}: {xhr.responseText}")
    return json.loads(xhr.responseText)


def default_transport() -> Transport:
    return _post_browser if sys.platform == "emscripten" else _post_cpython


def payload(topic: str, item: Scheduled) -> Dict:
    n = item.notification
    return {"topic": topic, "title": n.title, "message": n.message, "tags": list(n.tags),
            "priority": n.priority, "delay": str(int(item.at.timestamp()))}


def valid_topic(topic: str) -> bool:
    """ntfy 채널 이름 규칙: 영문·숫자·_·- 1~64자. 남이 추측하기 어렵게 12자 이상 권장."""
    return bool(topic) and len(topic) <= 64 and all(c.isalnum() or c in "_-" for c in topic) \
        and topic.isascii()


def publish(topic: str, item: Scheduled, transport: Optional[Transport] = None,
            server: Optional[str] = None) -> Dict:
    server = server or params.value("notify", "server")
    body = json.dumps(payload(topic, item), ensure_ascii=False).encode()
    return (transport or default_transport())(server, body)
