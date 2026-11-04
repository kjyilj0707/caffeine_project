"""오늘 추천의 타이머 화면 — iOS 타이머처럼 가운데 큰 링 + '다음 일정까지 남은 시간'.

일정 = 추천 잔(마시기) → 카페인 금지 시작 → 잘 시각. 링 가운데 숫자는 브라우저에서 1초마다 줄고,
시각이 지나면 다음 일정으로 넘어간다 (서버 왕복 없음). 링은 '이전 일정(처음엔 기상)부터 이 일정까지' 중
남은 비율만큼 남는다. 오늘이 아닌 날은 남은 시간 대신 시각을 보여준다.
"""
import json
from datetime import date, datetime, timedelta
from typing import Dict, List

import streamlit.components.v1 as components

from caffeine_engine.notify import local_tz

# 링 색: 평소 초록 → 10분 전 노랑 → 1분 전 빨강. 시간표 점·선은 한 가지 색
COLORS = {"normal": "#34C759", "soon": "#F5C400", "now": "#FF3B30"}
SOON_MIN, NOW_MIN = 10, 1


def _epoch_ms(day: date, h: float) -> int:
    midnight = datetime(day.year, day.month, day.day, tzinfo=local_tz())
    return int((midnight + timedelta(hours=h)).timestamp() * 1000)


def events(day: date, plan, servings, beverage_name: str, bed_h: float) -> List[Dict]:
    """화면에 쓸 일정 목록 (시간순). at = 그 시각(밀리초, 브라우저 Date와 같은 기준)."""
    out = [{"at": _epoch_ms(day, dose.time_h), "until": _epoch_ms(day, dose.end_h), "kind": "drink",
            "label": "다음 한 잔", "title": f"{beverage_name} {s.cup}",
            "sub": f"약 {s.ml:.0f}ml · {s.mg_actual:.0f}mg",
            "pace": f"{s.minutes}분 동안 나눠서 · {s.pace}" if s.minutes else ""}
           for dose, s in zip(plan.new_doses, servings)]
    if plan.cutoff_h is not None:
        out.append({"at": _epoch_ms(day, plan.cutoff_h), "kind": "stop", "label": "카페인 금지까지",
                    "title": "카페인 금지 시작", "sub": "이후엔 한 모금도 마시지 않기 (잠 보호)"})
    out.append({"at": _epoch_ms(day, bed_h), "kind": "bed", "label": "잘 시각까지", "title": "잘 시각",
                "sub": "잠든 뒤 몸속 카페인이 기준 아래로"})
    return sorted(out, key=lambda e: e["at"])


def render(day: date, wake_h: float, evts: List[Dict], live: bool, dark: bool) -> None:
    data = {"start": _epoch_ms(day, wake_h), "events": evts, "live": live, "colors": COLORS,
            "soon_ms": SOON_MIN * 60000, "now_ms": NOW_MIN * 60000,
            "fg": "#fafafa" if dark else "#111111", "muted": "#8b8d94" if dark else "#8a8a8f",
            "track": "rgba(250,250,250,.10)" if dark else "rgba(17,17,17,.07)",
            "bg": "#0e1117" if dark else "#ffffff", "line": "rgba(250,250,250,.10)" if dark else "rgba(17,17,17,.08)"}
    components.html(_HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)), height=372 + 58 * len(evts))


_HTML = """
<div id="w">
  <div class="ring">
    <svg viewBox="0 0 100 100"><circle class="track" cx="50" cy="50" r="46"/><circle id="arc" cx="50" cy="50" r="46"/></svg>
    <div class="center">
      <div id="top" class="top"></div>
      <div id="big" class="big"></div>
      <div id="title" class="title"></div>
      <div id="sub" class="sub"></div>
      <div id="pace" class="pace"></div>
    </div>
  </div>
  <div id="list" class="list"></div>
</div>
<style>
  :root { --fg: #111; --muted: #8a8a8f; }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: transparent; color: var(--fg);
               font-family: "Source Sans Pro", -apple-system, "Apple SD Gothic Neo", sans-serif; }
  #w { width: 100%; max-width: 420px; margin: 0 auto; }
  .ring { position: relative; width: min(100%, 340px); aspect-ratio: 1; margin: 0 auto 14px; }
  svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  circle { fill: none; stroke-width: 3.2; }
  #arc { stroke-linecap: round; transition: stroke-dashoffset .9s linear, stroke .3s; }
  .center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
            justify-content: center; text-align: center; padding: 0 14%; }
  .top { font-size: 17px; color: var(--muted); margin-bottom: 2px; }
  .big { font-size: 74px; font-weight: 300; letter-spacing: -1px; line-height: 1.05;
         font-variant-numeric: tabular-nums; }
  .big.long { font-size: 58px; }
  .title { font-size: 19px; font-weight: 600; margin-top: 10px; }
  .sub { font-size: 14px; color: var(--muted); margin-top: 3px; }
  .pace { font-size: 13px; color: var(--rail); margin-top: 4px; font-weight: 600; }
  .list { }
  .row { display: flex; align-items: center; gap: 14px; height: 58px; }
  /* 시간표: 점을 얇은 세로선으로 이음 (첫 점 위·마지막 점 아래는 선 없음) */
  .rail { position: relative; width: 12px; height: 100%; flex: none; display: flex; align-items: center; justify-content: center; }
  .rail::before, .rail::after { content: ""; position: absolute; left: 50%; width: 1.5px; transform: translateX(-50%);
                                background: var(--rail); }
  .rail::before { top: 0; bottom: 50%; }
  .rail::after { top: 50%; bottom: 0; }
  .row:first-child .rail::before, .row:last-child .rail::after { display: none; }
  .dot { position: relative; z-index: 1; width: 10px; height: 10px; border-radius: 50%; background: var(--rail);
         box-shadow: 0 0 0 3px var(--bg); }
  .row .t { font-size: 17px; font-weight: 600; min-width: 54px; font-variant-numeric: tabular-nums; }
  .row .t small { font-size: 12px; font-weight: 400; color: var(--muted); margin-left: 2px; }
  .row .n { flex: 1; font-size: 16px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row .r { font-size: 14px; color: var(--muted); white-space: nowrap; }
  .row.past { opacity: .4; }
</style>
<script>
const D = __DATA__;
const root = document.documentElement.style;
root.setProperty("--fg", D.fg); root.setProperty("--rail", D.colors.normal); root.setProperty("--bg", D.bg); root.setProperty("--muted", D.muted); root.setProperty("--line", D.line);
document.body.style.background = D.bg;
document.querySelector(".track").style.stroke = D.track;
const arc = document.getElementById("arc"), C = 2 * Math.PI * 46;
arc.style.strokeDasharray = C;
const pad = n => String(n).padStart(2, "0");
function hhmm(ms) { const d = new Date(ms + 9 * 3600e3); return pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()); }
function ampm(ms) { const d = new Date(ms + 9 * 3600e3), h = d.getUTCHours();
  return (h < 12 ? "오전 " : "오후 ") + ((h % 12) || 12) + ":" + pad(d.getUTCMinutes()); }
function clock(ms) { const s = Math.max(0, Math.ceil(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
  return h ? h + ":" + pad(m) + ":" + pad(s % 60) : pad(m) + ":" + pad(s % 60); }
function rel(ms) { if (ms > 0 && ms < 60000) return "곧"; const m = Math.round(ms / 60000), h = Math.floor(Math.abs(m) / 60), r = Math.abs(m) % 60;
  const t = (h ? h + "시간 " : "") + (r || !h ? r + "분" : "");
  return m >= 0 ? t.trim() + " 후" : t.trim() + " 전"; }
function draw() {
  const now = Date.now(), ev = D.events;
  const i = D.live ? ev.findIndex(e => (e.until || e.at) > now) : 0;   // 마시는 중인 잔도 '지금 일정'
  const paceEl = document.getElementById("pace");
  const top = document.getElementById("top"), big = document.getElementById("big");
  if (i < 0) {
    top.textContent = ""; big.textContent = "끝"; big.className = "big";
    document.getElementById("title").textContent = "오늘 일정이 끝났어요";
    document.getElementById("sub").textContent = "편히 주무세요";
    arc.style.stroke = D.track; arc.style.strokeDashoffset = 0;
  } else {
    const e = ev[i], prev = i ? (ev[i - 1].until || ev[i - 1].at) : D.start;
    paceEl.textContent = e.pace || "";
    if (D.live && e.until && now >= e.at) {          // 마시는 중: 링 = 마시는 시간 중 남은 비율
      const left = e.until - now, frac = left / Math.max(1, e.until - e.at);
      top.textContent = "마시는 중 · " + ampm(e.until) + "까지";
      big.textContent = clock(left); big.className = left >= 3600e3 ? "big long" : "big";
      arc.style.strokeDashoffset = C * (1 - frac); arc.style.stroke = D.colors.normal;
      document.getElementById("title").textContent = e.title;
      document.getElementById("sub").textContent = `지금쯤 ${Math.round((1 - frac) * 100)}% 마셨으면 좋아요`;
    } else if (D.live) {
      const left = e.at - now, frac = Math.min(1, Math.max(0, left / Math.max(1, e.at - prev)));
      top.textContent = e.label + " · " + ampm(e.at);
      big.textContent = clock(left); big.className = left >= 3600e3 ? "big long" : "big";
      arc.style.strokeDashoffset = C * (1 - frac);
      arc.style.stroke = left <= D.now_ms ? D.colors.now : left <= D.soon_ms ? D.colors.soon : D.colors.normal;
    } else {
      top.textContent = e.label; big.textContent = hhmm(e.at); big.className = "big";
      arc.style.strokeDashoffset = 0; arc.style.stroke = D.colors.normal;
    }
    if (!(D.live && e.until && now >= e.at)) {
      document.getElementById("title").textContent = e.title;
      document.getElementById("sub").textContent = e.sub;
    }
  }
  document.getElementById("list").innerHTML = ev.map((e, k) => {
    const past = D.live && (e.until || e.at) <= now, drinking = D.live && e.until && e.at <= now && now < e.until;
    const right = D.live ? (drinking ? "마시는 중" : past ? "지남" : rel(e.at - now))
                         : "기상 후 " + rel(e.at - D.start).replace(" 후", "");
    const when = e.until ? `${hhmm(e.at)}<small>~${hhmm(e.until)}</small>` : hhmm(e.at);
    return `<div class="row${past ? " past" : ""}"><span class="rail"><span class="dot"></span></span>` +
           `<span class="t">${when}</span><span class="n">${e.title}</span><span class="r">${right}</span></div>`;
  }).join("");
}
draw();
if (D.live) setInterval(draw, 1000);
</script>
"""
