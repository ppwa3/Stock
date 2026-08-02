"""
거래량 돌파 디스코드 알림 봇 (GitHub Actions 버전)
------------------------------------------------
- GitHub Actions가 5분마다 이 파일을 한 번씩 실행함 (while 루프 없음)
- 웹훅 URL은 코드에 넣지 않고 GitHub Secret(DISCORD_WEBHOOK)에서 읽음
- 이미 알린 종목은 state.json 에 기록해서 중복 알림 방지 (자정 KST 기준 초기화)
"""

import os
import json
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

# ===================== 설정 =====================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")  # GitHub Secret에서 읽음

WATCHLIST = {
    # --- 한국 주식 (모두 KOSPI 상장이라 .KS) ---
    "삼성전자":     "005930.KS",
    "SK하이닉스":   "000660.KS",
    "두산로보틱스": "454910.KS",
    "현대차":       "005380.KS",
    "현대모비스":   "012330.KS",
    "삼성전기":     "009150.KS",
    "SK스퀘어":     "402340.KS",
    "네이버":       "035420.KS",
    # --- 미국 주식 ---
    "Tesla":            "TSLA",
    "Apple":            "AAPL",
    "NVIDIA":           "NVDA",
    "Alphabet(Class A)": "GOOGL",
    "Microsoft":        "MSFT",
}

AVG_DAYS = 20          # 평균 거래량 / 이동평균선 계산 기간(일)
BREAKOUT_MULT = 2.0    # 거래량이 평균 대비 몇 배 이상이면 '돌파'로 볼지
ONLY_UP = False        # True면 '상승하면서 거래량 터진 것'만 알림
MIN_ABS_CHANGE = 0.0   # 전일 대비 최소 몇 % 이상 움직여야 알림 (0이면 제한 없음)
STATE_FILE = "state.json"
KST = timezone(timedelta(hours=9))  # 한국 시간 (자정 리셋 기준)

# ================================================================


def send_discord(message: str):
    requests.post(DISCORD_WEBHOOK, json={"content": message})


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"date": "", "alerted": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def check_volume_breakout(name: str, ticker: str):
    df = yf.download(ticker, period="3mo", interval="1d",
                     progress=False, auto_adjust=True)
    if df.empty or len(df) < AVG_DAYS + 1:
        return None

    volumes = df["Volume"].squeeze()
    closes = df["Close"].squeeze()

    today_vol = float(volumes.iloc[-1])
    avg_vol = float(volumes.iloc[-(AVG_DAYS + 1):-1].mean())
    if avg_vol == 0:
        return None
    vol_ratio = today_vol / avg_vol
    if vol_ratio < BREAKOUT_MULT:
        return None

    today_close = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    pct_change = (today_close / prev_close - 1) * 100
    if abs(pct_change) < MIN_ABS_CHANGE:
        return None
    if ONLY_UP and pct_change <= 0:
        return None

    above_ma = today_close >= float(closes.iloc[-AVG_DAYS:].mean())

    return {
        "name": name, "ticker": ticker, "pct": pct_change,
        "ratio": vol_ratio, "close": today_close, "above_ma": above_ma,
    }


def build_combined_message(hits: list) -> str:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    lines = [f"🚨 거래량 돌파 알림 ({now} KST)", "─" * 22]
    for h in hits:
        arrow = "📈" if h["pct"] > 0 else "📉"
        trend = "추세 양호" if h["above_ma"] else "추세 약함"
        lines.append(
            f"{arrow} {h['name']} ({h['ticker']})  "
            f"{h['pct']:+.2f}%  |  거래량 {h['ratio']:.1f}배  |  {trend}  |  {h['close']:,.2f}"
        )
    return "\n".join(lines)


def main():
    if not DISCORD_WEBHOOK:
        print("⚠ DISCORD_WEBHOOK 이 비어 있습니다. GitHub Secret을 확인하세요.")
        return

    today = datetime.now(KST).strftime("%Y-%m-%d")
    state = load_state()
    if state.get("date") != today:          # 날짜 바뀌면 초기화
        state = {"date": today, "alerted": []}
    alerted = set(state["alerted"])

    new_hits = []
    for name, ticker in WATCHLIST.items():
        try:
            info = check_volume_breakout(name, ticker)
            if info and ticker not in alerted:
                new_hits.append(info)
                alerted.add(ticker)
        except Exception as e:
            print(f"에러 ({name}): {e}")

    if new_hits:
        send_discord(build_combined_message(new_hits))
        print(f"새 돌파 {len(new_hits)}개 전송:", ", ".join(h["name"] for h in new_hits))
    else:
        print("새 돌파 없음")

    state["alerted"] = sorted(alerted)
    save_state(state)


if __name__ == "__main__":
    main()
