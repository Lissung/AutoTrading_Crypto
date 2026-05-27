import json
import time
import os
import schedule
from core.api_client import BinanceClient
from core.logger import logger
from core.telegram_notifier import TelegramNotifier
from strategies.custom_logic_v1 import CustomLogicV1

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config.json: {e}")
        return None

def get_ignored_tickers(api):
    """현재 이미 보유 중인 코인들을 파악하여 건드리지 않도록 무시 목록을 생성/로드합니다."""
    ignored_file = os.path.join(os.path.dirname(__file__), 'ignored_tickers.json')
    if os.path.exists(ignored_file):
        with open(ignored_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    ignored = []
    if api.binance:
        balances = api.get_balances()
        for currency, amount in balances.items():
            if currency != 'USDT' and float(amount) > 0:
                ignored.append(f"{currency}/USDT")
                
        with open(ignored_file, 'w', encoding='utf-8') as f:
            json.dump(ignored, f, ensure_ascii=False, indent=4)
            
        if ignored:
            logger.info(f"🔒 [기존 코인 보호 모드] 다음 코인들은 봇이 건드리지 않습니다: {ignored}")
            
    return ignored

def main():
    logger.info("=== 🚀 바이낸스 자동매매 봇 시작 ===")
    config = load_config()
    if not config:
        return
        
    trade_amount_usdt = config.get("TRADE_AMOUNT_USDT", 10.0)
    interval = config.get("CHECK_INTERVAL_SECONDS", 30)
    
    # 1. API 클라이언트, 전략, 텔레그램 초기화
    api = BinanceClient()
    strategy = CustomLogicV1(api)
    notifier = TelegramNotifier()
    
    # 시작 알림
    notifier.send_message("<b>[봇 시작]</b>\n바이낸스 자동매매 봇이 가동되었습니다. 🚀")
    
    # 기존 보유 코인 보호 모드
    ignored_tickers = get_ignored_tickers(api)
    
    # 2. 거래 시작
    
    def trade_job():
        # 매 주기마다 거래량 상위 50개 종목을 새로 가져옵니다.
        tickers = api.get_top_volume_tickers(limit=50)
        logger.info(f"👀 현재 감시 중인 상위 거래량 종목(50개): {tickers[:5]}... 등")
        
        for ticker in tickers:
            if ticker in ignored_tickers:
                continue # 이미 수동으로 사둔 코인은 감시 제외
                
            # USDT 마켓 전용: 혹시라도 /USDT가 아닌 심볼이 들어오면 스킵
            if not ticker.endswith('/USDT'):
                logger.warning(f"⚠️ [{ticker}] USDT 마켓이 아니므로 스킵합니다.")
                continue
                
            try:
                # Base currency 추출 (예: BTC/USDT -> BTC)
                base_currency = ticker.split('/')[0]
                
                # 1. 매도 조건 검사 (보유 중인 경우)
                balance = api.get_balance(base_currency)
                
                # 거래소 수수료나 먼지(dust) 코인을 고려하여 최소 임계값 설정 (예: 0이 아니면 매도 시도)
                # 엄밀히는 해당 코인의 최소 거래수량을 확인해야 하지만 여기서는 단순화합니다.
                # 잔고 가치가 5 USDT 이상일 때 보유중인 것으로 간주 (먼지 무시)
                current_price = api.get_current_price(ticker)
                balance_usdt_value = balance * current_price if current_price else 0
                
                if balance_usdt_value > 5.0: # 보유 가치가 5 USDT 이상이면
                    if strategy.check_sell_condition(ticker):
                        avg_buy_price, buy_timestamp = api.get_last_buy_info(ticker)
                        sell_price = current_price if current_price else api.get_current_price(ticker)
                        profit_rate = 0.0
                        if avg_buy_price > 0 and sell_price:
                            profit_rate = (sell_price - avg_buy_price) / avg_buy_price * 100
                            
                        # 경과 시간 및 강제 매도 여부 계산
                        elapsed_hours = 0.0
                        is_force_sell = False
                        if buy_timestamp > 0:
                            elapsed_seconds = (time.time() * 1000 - buy_timestamp) / 1000
                            elapsed_hours = elapsed_seconds / 3600
                            if elapsed_seconds >= 86400:
                                is_force_sell = True
                                
                        order = api.sell_market_order(ticker, balance)
                        if order:
                            reason = "⏳ 24시간 초과 강제 매도" if is_force_sell else "🎯 조건 달성 매도"
                            logger.info(f"✅ {ticker} 전량 매도 완료 (수익률: {profit_rate:+.2f}%, 사유: {reason})")
                            
                            # 매도 완료 직후 지갑에 남는 미세 잔돈(Dust) BNB 전환 시도 (1초 대기 후 진행)
                            time.sleep(1.0)
                            dust_res = api.convert_dust_to_bnb(base_currency)
                            dust_msg = ""
                            if dust_res:
                                dust_msg = "\n🧹 <b>잔돈 청소</b>: 미세 소수점 잔돈을 BNB로 일괄 전환했습니다."
                            
                            notifier.send_message(
                                f"🚨 <b>매도 완료 ({reason})</b>\n"
                                f"- 코인: {ticker}\n"
                                f"- 수량: {balance:.4f}\n"
                                f"- 매수가: {avg_buy_price:.6f}\n"
                                f"- 매도가: {sell_price:.6f}\n"
                                f"- 경과 시간: {elapsed_hours:.1f}시간\n"
                                f"- <b>수익률: {profit_rate:+.2f}%</b>"
                                f"{dust_msg}"
                            )
                    continue # 보유 중일 때는 매수 조건 검사를 건너뜀
                    
                # 2. 매수 조건 검사 (보유 중이 아닌 경우)
                if strategy.check_buy_condition(ticker):
                    usdt_balance = api.get_balance("USDT")
                    if usdt_balance >= trade_amount_usdt:
                        order = api.buy_market_order(ticker, trade_amount_usdt)
                        if order:
                            logger.info(f"✅ {ticker} {trade_amount_usdt} USDT 매수 완료")
                            notifier.send_message(f"🚀 <b>매수 완료</b>\n- 코인: {ticker}\n- 금액: {trade_amount_usdt} USDT")
                    else:
                        logger.warning(f"⚠️ 매수 실패: USDT 잔고 부족 (현재 잔고: {usdt_balance} USDT)")
                        
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                
            time.sleep(0.5) # 바이낸스 API Rate Limit(호출 제한) 방지

    # 3. 스케줄러 등록
    schedule.every(interval).seconds.do(trade_job)
    
    logger.info(f"봇이 정상적으로 실행 중입니다. ({interval}초마다 감시)")
    
    # 4. 무한 루프
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("=== 🛑 봇 실행을 종료합니다 ===")
        notifier.send_message("<b>[봇 종료]</b>\n사용자에 의해 봇 가동이 중단되었습니다. 🛑")

if __name__ == "__main__":
    main()
