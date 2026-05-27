import ccxt
import json
import os
from core.logger import logger

class BinanceClient:
    def __init__(self):
        self.binance = None
        self._load_keys()
        
    def _load_keys(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            api_key = config.get("BINANCE_API_KEY")
            secret = config.get("BINANCE_SECRET_KEY")
            
            if api_key and secret and "여기에_바이낸스" not in api_key:
                self.binance = ccxt.binance({
                    'apiKey': api_key,
                    'secret': secret,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot' # 현물 마켓 지정
                    }
                })
                logger.info("✅ 바이낸스 API 키 로드 성공 (실전 매매 권한 획득)")
            else:
                self.binance = ccxt.binance({'enableRateLimit': True})
                logger.warning("⚠️ 바이낸스 API 키가 설정되지 않았습니다. 현재가 조회 기능만 동작합니다.")
        except FileNotFoundError:
            self.binance = ccxt.binance({'enableRateLimit': True})
            logger.error("❌ config.json 파일을 찾을 수 없습니다.")

    def get_current_price(self, ticker="BTC/USDT"):
        try:
            ticker_info = self.binance.fetch_ticker(ticker)
            return ticker_info['last']
        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            return None
        
    def get_balance(self, currency="USDT"):
        """특정 코인(또는 USDT)의 사용 가능한(free) 잔고를 조회"""
        if not self.binance or not self.binance.apiKey:
            return 0
        try:
            balance = self.binance.fetch_balance()
            if currency in balance:
                return float(balance[currency]['free'])
            return 0
        except Exception as e:
            logger.error(f"Error fetching balance for {currency}: {e}")
            return 0

    def get_balances(self):
        """보유 중인 전체 코인 잔고 조회 (무시 목록 생성용)"""
        if not self.binance or not self.binance.apiKey:
            return {}
        try:
            balance = self.binance.fetch_balance()
            return balance['total'] # {'BTC': 0.1, 'USDT': 100} 형태로 반환
        except Exception as e:
            logger.error(f"Error fetching all balances: {e}")
            return {}

    def buy_market_order(self, ticker, amount_usdt):
        """USDT 금액으로 시장가 매수 (quoteOrderQty 방식 - USDT 마켓 전용)"""
        if not self.binance or not self.binance.apiKey:
            return None
        
        # USDT 마켓인지 강제 검증
        if not ticker.endswith('/USDT'):
            logger.error(f"❌ [매수 거부] {ticker}는 USDT 마켓이 아닙니다. USDT 페어만 거래 가능합니다.")
            return None
        
        try:
            # quoteOrderQty 방식: USDT 금액으로 직접 매수 (바이낸스가 수량 자동 계산)
            # 이 방식은 소수점 정밀도 문제 없이 정확한 USDT 금액만큼 매수합니다.
            self.binance.load_markets()
            logger.info(f"🚀 [매수 주문] 종목: {ticker}, 금액: {amount_usdt} USDT (quoteOrderQty 방식)")
            return self.binance.create_market_buy_order(
                ticker,
                amount=None,  # 수량 대신 금액으로 지정
                params={'quoteOrderQty': amount_usdt}  # USDT 금액으로 직접 매수
            )
        except Exception as e:
            logger.error(f"Buy error {ticker}: {e}")
            return None
        
    def sell_market_order(self, ticker, volume):
        if not self.binance or not self.binance.apiKey:
            return None
        try:
            # 거래소 마켓 정보 로드 및 수량 정밀도 절사
            self.binance.load_markets()
            precise_volume = float(self.binance.amount_to_precision(ticker, volume))
            
            if precise_volume <= 0:
                logger.warning(f"⚠️ 정밀도 절사 후 매도 수량이 0 이하입니다. ({volume} -> {precise_volume})")
                return None
                
            logger.info(f"📉 [매도 주문] 종목: {ticker}, 수량: {precise_volume} (원본 잔고: {volume})")
            return self.binance.create_market_sell_order(ticker, precise_volume)
        except Exception as e:
            logger.error(f"Sell error {ticker}: {e}")
            return None
            
    def get_avg_buy_price(self, ticker):
        """가장 최근에 체결된 해당 티커의 매수 가격을 조회합니다."""
        if not self.binance or not self.binance.apiKey:
            return 0
        try:
            trades = self.binance.fetch_my_trades(ticker, limit=10)
            for trade in reversed(trades): # 최신 거래부터 거꾸로 확인
                if trade['side'] == 'buy':
                    return float(trade['price'])
            return 0
        except Exception as e:
            logger.error(f"Error fetching avg buy price for {ticker}: {e}")
            return 0

    def get_last_buy_info(self, ticker):
        """가장 최근에 체결된 해당 티커의 매수 가격과 시간(timestamp)을 조회합니다."""
        if not self.binance or not self.binance.apiKey:
            return 0, 0
        try:
            trades = self.binance.fetch_my_trades(ticker, limit=10)
            for trade in reversed(trades): # 최신 거래부터 거꾸로 확인
                if trade['side'] == 'buy':
                    return float(trade['price']), int(trade['timestamp'])
            return 0, 0
        except Exception as e:
            logger.error(f"Error fetching last buy info for {ticker}: {e}")
            return 0, 0

    def convert_dust_to_bnb(self, base_currency):
        """매도 후 남은 소액 잔돈(dust)을 BNB로 전환합니다."""
        if not self.binance or not self.binance.apiKey:
            return None
        try:
            # 먼저 현재 잔고 조회
            balance = self.get_balance(base_currency)
            if balance <= 0:
                return None
                
            # 너무 큰 금액을 실수로 전환하는 것을 방지하기 위해 잔고 가치를 체크합니다.
            # 1.5 USDT 미만의 가치만 먼지 전환 대상으로 삼습니다.
            current_price = self.get_current_price(f"{base_currency}/USDT")
            if current_price:
                value_usdt = balance * current_price
                if value_usdt > 1.5:  # 1.5 USDT 초과 보유 중이면 Dust 전환 대상이 아님
                    logger.info(f"ℹ️ {base_currency} 잔고 가치가 {value_usdt:.2f} USDT로, 먼지 전환 기준(1.5 USDT)을 초과하므로 스킵합니다.")
                    return None
            
            logger.info(f"🧹 [잔돈 청소] {base_currency} 잔고 {balance}개를 BNB로 일괄 전환 시도...")
            # 바이낸스 Dust 전환 API 호출 (sapiPostAssetDust)
            response = self.binance.sapiPostAssetDust({'asset': [base_currency]})
            logger.info(f"✅ {base_currency} 잔돈 BNB 전환 성공: {response}")
            return response
        except Exception as e:
            logger.error(f"Error converting dust to BNB for {base_currency}: {e}")
            return None

    def get_top_volume_tickers(self, limit=50):
        """24시간 거래량 상위 USDT 마켓 리스트를 가져옵니다. (USDT 페어 전용)"""
        try:
            # 전체 티커 정보 한 번에 가져오기
            tickers = self.binance.fetch_tickers()
            
            # USDT 마켓만 엄격하게 필터링 (심볼이 정확히 'XXX/USDT' 형태여야 함)
            usdt_tickers = []
            for symbol, data in tickers.items():
                # 반드시 /USDT로 끝나는 심볼만 허용 (예: BTC/USDT는 OK, BTC/USDT:USDT 같은 선물은 제외)
                if not symbol.endswith('/USDT'):
                    continue
                if data['quoteVolume'] is None:
                    continue
                # 스테이블코인 및 법정화폐 토큰 제외
                base = symbol.split('/')[0]
                if base in ['USDC', 'BUSD', 'TUSD', 'PAX', 'DAI', 'EUR', 'GBP', 'FDUSD', 'USDP', 'USDS']:
                    continue
                usdt_tickers.append(data)
            
            # 거래량(quoteVolume) 기준 내림차순 정렬
            sorted_tickers = sorted(usdt_tickers, key=lambda x: x['quoteVolume'], reverse=True)
            
            # 상위 N개 심볼만 반환 (모두 /USDT 마켓 보장)
            result = [t['symbol'] for t in sorted_tickers[:limit]]
            logger.info(f"✅ USDT 마켓 전용 상위 {len(result)}개 종목 조회 완료")
            return result
        except Exception as e:
            logger.error(f"Error fetching top volume tickers: {e}")
            return ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT", "DOGE/USDT"] # 실패 시 기본값 (모두 USDT 페어)
