import json
import time
import os
import socket
import sys
import signal
import schedule
from core.api_client import BinanceClient
from core.logger import logger
from core.telegram_notifier import TelegramNotifier
from strategies.custom_logic_v1 import CustomLogicV1

# ─────────────────────────────────────────────────────────────
# PID 잠금 파일 경로 (같은 컴퓨터 내 중복 실행 방지용)
# ─────────────────────────────────────────────────────────────
PID_FILE = os.path.join(os.path.dirname(__file__), '.bot.pid')
HOSTNAME = socket.gethostname()  # 현재 컴퓨터 이름

def acquire_lock():
    """PID 잠금 파일을 획득하여 같은 컴퓨터에서 봇이 중복 실행되는 것을 방지합니다."""
    if os.path.exists(PID_FILE):
        with open(PID_FILE, 'r') as f:
            old_pid = int(f.read().strip())
        # 이전 PID가 아직 살아있는지 확인
        try:
            os.kill(old_pid, 0)  # 시그널 0 = 프로세스 존재 확인만
            logger.error(f"❌ 이미 이 컴퓨터에서 봇이 실행 중입니다! (PID: {old_pid}). 종료합니다.")
            return False
        except OSError:
            logger.warning(f"⚠️ 이전 PID 파일({old_pid})이 남아있지만 프로세스가 없습니다. 덮어씁니다.")

    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    logger.info(f"🔒 PID 잠금 획득: PID={os.getpid()}, 컴퓨터={HOSTNAME}")
    return True

def release_lock():
    """종료 시 PID 잠금 파일을 삭제합니다."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        logger.info("🔓 PID 잠금 해제 완료.")

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
    # ── 1. 같은 컴퓨터 중복 실행 방지 ────────────────────────
    if not acquire_lock():
        sys.exit(1)

    # 종료 시그널(Ctrl+C, kill 명령 등) 처리 등록
    def graceful_shutdown(signum=None, frame=None):
        logger.info("=== 🛑 봇 프로세스를 완전 종료합니다 ===")
        notifier.send_message(
            f"<b>[봇 프로세스 종료]</b>\n"
            f"봇이 완전히 종료되었습니다. 🛑\n"
            f"- 컴퓨터: {HOSTNAME}"
        )
        release_lock()
        sys.exit(0)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    # ── 일시정지 상태 플래그 (텔레그램 /stop, /start 로 제어) ──
    bot_state = {"paused": False}  # dict로 감싸야 중첩함수에서 수정 가능

    logger.info("=== 🚀 바이낸스 자동매매 봇 시작 ===")
    config = load_config()
    if not config:
        release_lock()
        return
        
    trade_amount_usdt = config.get("TRADE_AMOUNT_USDT", 10.0)
    interval = config.get("CHECK_INTERVAL_SECONDS", 30)
    
    # API 클라이언트, 전략, 텔레그램 초기화
    api = BinanceClient()
    strategy = CustomLogicV1(api)
    notifier = TelegramNotifier()
    
    # 시작 알림 (어떤 컴퓨터에서 기동했는지 표기)
    notifier.send_message(
        f"<b>[봇 시작]</b>\n"
        f"바이낸스 자동매매 봇이 가동되었습니다. 🚀\n"
        f"- 컴퓨터: {HOSTNAME}\n"
        f"- 전체잔고 사용: {'✅ ON' if config.get('TRADE_ALL_USDT', False) else '❌ OFF (고정: ' + str(trade_amount_usdt) + ' USDT)'}\n"
        f"<i>봇을 원격 종료하려면 /stop 을 전송하세요.</i>"
    )
    
    # 기존 보유 코인 보호 모드
    ignored_tickers = get_ignored_tickers(api)
    
    # ── 텔레그램 명령 체크 함수 (/stop, /start) ─────────────────
    def check_telegram_command():
        """텔레그램에서 /stop 또는 /start 명령을 수신하여 봇 상태를 제어합니다."""
        command = notifier.get_latest_command()

        if command == "/stop" and not bot_state["paused"]:
            logger.info("📲 텔레그램 /stop 수신 → 거래를 일시정지합니다.")
            bot_state["paused"] = True
            notifier.send_message(
                f"⏸ <b>[거래 일시정지]</b>\n"
                f"/stop 명령을 수신했습니다.\n"
                f"거래가 중단되었습니다. (봇 프로세스는 유지)\n"
                f"- 컴퓨터: {HOSTNAME}\n"
                f"<i>재개하려면 /start 를 전송하세요.</i>"
            )

        elif command == "/start" and bot_state["paused"]:
            logger.info("📲 텔레그램 /start 수신 → 거래를 재개합니다.")
            bot_state["paused"] = False
            notifier.send_message(
                f"▶️ <b>[거래 재개]</b>\n"
                f"/start 명령을 수신했습니다.\n"
                f"거래가 재개되었습니다. 🚀\n"
                f"- 컴퓨터: {HOSTNAME}"
            )

    # ── 거래 루프 ─────────────────────────────────────────────
    def trade_job():
        # 텔레그램 명령 체크 (매 주기 실행 - 일시정지/재개)
        check_telegram_command()

        # 일시정지 상태이면 거래 건너뜀
        if bot_state["paused"]:
            logger.info("⏸ [일시정지 중] 거래를 건너뜁니다. 재개하려면 /start 를 전송하세요.")
            return
        
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
                                
                            # BNB 잔고가 매도 최소 금액을 초과하는지 체크하여 현금화 시도
                            try:
                                bnb_sold_value = api.sell_bnb_to_usdt_if_possible()
                                if bnb_sold_value:
                                    dust_msg += f"\n🪙 <b>BNB 현금화</b>: BNB 잔고가 최소 주문 금액을 초과하여 {bnb_sold_value:.2f} USDT로 매도/현금화했습니다."
                            except Exception as e:
                                logger.error(f"Error executing sell_bnb_to_usdt_if_possible: {e}")
                                
                            # 매도 완료 후 최종 USDT 잔액 조회
                            post_sell_usdt_balance = api.get_balance("USDT")
                            
                            notifier.send_message(
                                f"🚨 <b>매도 완료 ({reason})</b>\n"
                                f"- 코인: {ticker}\n"
                                f"- 수량: {balance:.4f}\n"
                                f"- 매수가: {avg_buy_price:.6f}\n"
                                f"- 매도가: {sell_price:.6f}\n"
                                f"- 경과 시간: {elapsed_hours:.1f}시간\n"
                                f"- <b>수익률: {profit_rate:+.2f}%</b>\n"
                                f"- <b>보유 USDT: {post_sell_usdt_balance:.2f} USDT</b>"
                                f"{dust_msg}"
                            )
                    continue # 보유 중일 때는 매수 조건 검사를 건너뜀
                    
                # 2. 매수 조건 검사 (보유 중이 아닌 경우)
                if strategy.check_buy_condition(ticker):
                    usdt_balance = api.get_balance("USDT")
                    
                    # 지갑의 모든 USDT를 사용하는 옵션 적용 (TRADE_ALL_USDT)
                    if config.get("TRADE_ALL_USDT", False):
                        # 급등 시 슬리피지 및 수수료 버퍼를 위해 99% 사용
                        current_trade_amount = usdt_balance * 0.99
                    else:
                        current_trade_amount = trade_amount_usdt
                        
                    # 최소 거래 금액 안전망 (예: 10 USDT)
                    min_trade_limit = 10.0
                    if current_trade_amount < min_trade_limit:
                        logger.warning(f"⚠️ 매수 스킵: 주문 금액({current_trade_amount:.2f} USDT)이 최소 거래 제한({min_trade_limit} USDT) 미만입니다. (현재 USDT 잔고: {usdt_balance:.2f} USDT)")
                        continue
                        
                    if usdt_balance >= current_trade_amount:
                        order = api.buy_market_order(ticker, current_trade_amount)
                        if order:
                            logger.info(f"✅ {ticker} {current_trade_amount:.2f} USDT 매수 완료")
                            invested_ratio = (current_trade_amount / usdt_balance) * 100 if usdt_balance > 0 else 0.0
                            notifier.send_message(
                                f"🚀 <b>매수 완료</b>\n"
                                f"- 코인: {ticker}\n"
                                f"- 금액: {current_trade_amount:.2f} USDT\n"
                                f"- <b>투자 비중: {invested_ratio:.1f}%</b> (보유 {usdt_balance:.2f} USDT 중)"
                            )
                    else:
                        logger.warning(f"⚠️ 매수 실패: USDT 잔고 부족 (현재 잔고: {usdt_balance:.2f} USDT, 필요 금액: {current_trade_amount:.2f} USDT)")
                        
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                
            time.sleep(0.5) # 바이낸스 API Rate Limit(호출 제한) 방지

    # 스케줄러 등록
    schedule.every(interval).seconds.do(trade_job)
    
    logger.info(f"봇이 정상적으로 실행 중입니다. ({interval}초마다 감시)")
    
    # 무한 루프
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        graceful_shutdown()

if __name__ == "__main__":
    main()
