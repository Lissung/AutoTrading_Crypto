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
        if not self.binance or not self.binance.apiKey:
            return None
        try:
            # 바이낸스 시장가 매수는 달러(USDT) 대신 코인 수량(Amount)을 요구합니다.
            current_price = self.get_current_price(ticker)
            if not current_price:
                return None
            
            # 주문 수량 = 달러 / 현재가
            amount = amount_usdt / current_price
            
            logger.info(f"🚀 [매수 주문] 종목: {ticker}, {amount_usdt} USDT (약 {amount:.4f}개)")
            return self.binance.create_market_buy_order(ticker, amount)
        except Exception as e:
            logger.error(f"Buy error {ticker}: {e}")
            return None
        
    def sell_market_order(self, ticker, volume):
        if not self.binance or not self.binance.apiKey:
            return None
        try:
            logger.info(f"📉 [매도 주문] 종목: {ticker}, 수량: {volume}")
            return self.binance.create_market_sell_order(ticker, volume)
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
