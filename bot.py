"""
관심종목 거래량 현황 봇 (GitHub Actions 버전) - 전체 리포트형
------------------------------------------------
- 5분마다(GitHub Actions cron) 감시 목록 '전체'를 디스코드로 보냄
- 각 종목: 현재가 / 전일대비 % / 거래량 배수 / 추세 / 거래량 돌파 여부
- 거래량 돌파(기본 2배 이상) 종목은 🚨 표시하고 맨 위로 정렬
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
BREAKOUT_MULT = 2.0    # 이 배수 이상이면 '거래량 돌파'로 🚨 표시
STATE_FILE = "state.json"
KST = timezone(timedelta(hours=9))

# ================================================================


def send_discord(message: str):
    requests.post(DISCORD_WEBHOOK, json={"content": message})


def get_stock_info(name: str, ticker: str):
    df = yf.download(ticker, period="3mo", interval="1d",
                     progress=False, auto_adjust=True)
    if df.empty or len(df) < AVG_DAYS + 1:
        return {"name": name, "ticker": ticker, "ok": False}

    volumes = df["Volume"].squeeze()
    closes = df["Close"].squeeze()

    today_vol = float(volumes.iloc[-1])
    avg_vol = float(volumes.iloc[-(AVG_DAYS + 1):-1].mean())
    vol_ratio = today_vol / avg_vol if avg_vol else 0.0

    today_close = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    pct = (today_close / prev_close - 1) * 100
    above_ma = today_close >= float(closes.iloc[-AVG_DAYS:].mean())

    return {
        "name": name, "ticker": ticker, "ok": True,
        "close": today_close, "pct": pct, "ratio": vol_ratio,
        "above_ma": above_ma, "breakout": vol_ratio >= BREAKOUT_MULT,
    }


def format_line(info: dict) -> str:
    if not info["ok"]:
        return f"⚠️ {info['name']} ({info['ticker']})  데이터 없음"
    arrow = "📈" if info["pct"] >= 0 else "📉"
    flag = "🚨 " if info["breakout"] else ""
    trend = "추세 양호" if info["above_ma"] else "추세 약함"
    hot = " (돌파!)" if info["breakout"] else ""
    return (
        f"{flag}{arrow} {info['name']} ({info['ticker']})\n"
        f"      {info['close']:,.2f}  |  전일 {info['pct']:+.2f}%  |  "
        f"거래량 {info['ratio']:.1f}배{hot}  |  {trend}"
    )


def main():
    if not DISCORD_WEBHOOK:
        print("⚠ DISCORD_WEBHOOK 이 비어 있습니다. GitHub Secret을 확인하세요.")
        return

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    infos = []
    for name, ticker in WATCHLIST.items():
        try:
            infos.append(get_stock_info(name, ticker))
        except Exception as e:
            print(f"에러 ({name}): {e}")
            infos.append({"name": name, "ticker": ticker, "ok": False})

    # 거래량 돌파 종목을 맨 위로, 그다음 거래량 배수 높은 순
    infos.sort(key=lambda x: (not x.get("breakout", False), -(x.get("ratio") or 0)))
    breakout_count = sum(1 for i in infos if i.get("breakout"))

    header = [
        f"📊 관심종목 현황 ({now})",
        f"거래량 돌파 {breakout_count}종목  ·  돌파 기준: {AVG_DAYS}일 평균의 {BREAKOUT_MULT}배 이상",
        "━" * 22,
    ]
    body = [format_line(i) for i in infos]
    legend = [
        "",
        "─ 보는 법 ─",
        "🚨 거래량 돌파 종목  ·  📈 상승 / 📉 하락 (전일 대비)",
        "거래량 N배 = 최근 20일 평균 거래량 대비  ·  추세 = 20일 이동평균선 위(양호)/아래(약함)",
    ]
    send_discord("\n".join(header + body + legend))
    print(f"전송 완료. 전체 {len(infos)}종목, 돌파 {breakout_count}종목.")

    # state.json 은 날짜만 저장 → 하루 1회만 바뀌어서 커밋 스팸 방지 + 저장소 활동 유지
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": datetime.now(KST).strftime("%Y-%m-%d")}, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
