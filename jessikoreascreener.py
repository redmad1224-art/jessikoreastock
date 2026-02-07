import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import os
import requests

# ============================================================
# ⚙️ 텔레그램 설정 및 발송 함수
# ============================================================
def send_telegram_msg(message):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {'chat_id': chat_id, 'text': message}
        try:
            res = requests.post(url, params=params)
            print(f"텔레그램 전송 시도 결과: {res.status_code}")
        except Exception as e:
            print(f"텔레그램 발송 중 오류: {e}")

# ================= : 기존 전략 설정 (유지) : =================
PEAK_BALANCE = 40_000_000      
RISK_PCT = 0.5                  

def position_sizing(entry_price, stop_price):
    risk_amount = PEAK_BALANCE * (RISK_PCT / 100)
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk <= 0: return 0, 0, 0
    qty = int(risk_amount / per_share_risk)
    invested = int(qty * entry_price)
    max_loss = int(qty * per_share_risk)
    return qty, invested, max_loss

def analyze_stock(code, name):
    try:
        df = fdr.DataReader(code).tail(120)
        if len(df) < 100: return None
        price = df['Close'].iloc[-1]
        if price < 1000: return None
        avg_turnover = (df['Close'] * df['Volume']).tail(20).mean()
        if avg_turnover < 1_000_000_000: return None
        ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        ema100 = df['Close'].ewm(span=100).mean().iloc[-1]
        if not (ema20 > ema50 > ema100): return None
        tr = pd.concat([df['High'] - df['Low'], abs(df['High'] - df['Close'].shift()), abs(df['Low'] - df['Close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = atr / price * 100
        if atr_pct < 3: return None
        avg_vol = df['Volume'].tail(20).mean()
        rel_vol = df['Volume'].iloc[-1] / avg_vol
        if rel_vol < 1.5: return None
        recent_high = df['High'].tail(60).max()
        if price < recent_high * 0.98: return None
        stop_loss = max(price - 2 * atr, ema20)
        qty, invested, max_loss = position_sizing(price, stop_loss)
        if qty <= 0: return None
        breakout_type = "신고가" if price >= recent_high else "고점근접"
        return {
            "Name": name, "Price": int(price), "StopLoss": int(stop_loss),
            "Qty": qty, "RelVol": round(rel_vol, 2), "Type": breakout_type
        }
    except: return None

# ============================================================
# 3. 메인 실행 (수정됨)
# ============================================================
def main():
    print("=== 돌파 스크리너 실행 중 ===")
    kospi = fdr.StockListing('KOSPI')
    kosdaq = fdr.StockListing('KOSDAQ')
    universe = pd.concat([kospi, kosdaq])
    tasks = [(row['Code'], row['Name']) for _, row in universe.iterrows()]
    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(analyze_stock, code, name) for code, name in tasks]
        for future in futures:
            res = future.result()
            if res: results.append(res)

    if results:
        df_res = pd.DataFrame(results)
        df_res.to_csv("result.csv", index=False, encoding="utf-8-sig")
        
        # 텔레그램 메시지 생성
        msg = f"🚀 {datetime.now().strftime('%Y-%m-%d')} 돌파 종목 ({len(results)}개)\n"
        for _, row in df_res.iterrows():
            msg += f"\n- {row['Name']}: {row['Price']}원 (손절: {row['StopLoss']} / 수량: {row['Qty']}주)"
        
        send_telegram_msg(msg)
        print("✅ 분석 완료 및 텔레그램 발송 성공!")
    else:
        send_telegram_msg("😴 오늘은 조건에 맞는 종목이 없습니다.")
        print("조건에 맞는 종목 없음.")

if __name__ == "__main__":
    main()
