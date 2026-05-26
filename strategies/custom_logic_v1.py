from strategies.base_strategy import BaseStrategy
from core.logger import logger
import time

class CustomLogicV1(BaseStrategy):
    """
    급등주 포착 전략 V1 (바이낸스 버전)
    - 매수 조건: 3분 전 대비 2% 이상 상승 AND 5분 전 대비 5% 이상 상승
    - 매도 조건: 매수가 대비 10% 이상 상승 시 익절 OR 5% 이상 하락 시 손절
    """
    def __init__(self, api_client):
        super().__init__(api_client)
        
    def check_buy_condition(self, ticker) -> bool:
        try:
            # ccxt로 1분봉 데이터 6개 가져오기
            # 데이터 구조: [ [timestamp, open, high, low, close, volume], ... ]
            ohlcv = self.api.binance.fetch_ohlcv(ticker, timeframe='1m', limit=6)
            if not ohlcv or len(ohlcv) < 6:
                return False
                
            current_price = ohlcv[-1][4]  # 인덱스 4가 종가(close)
            price_3m_ago = ohlcv[-4][4]   # 현재(-1), 1분전(-2), 2분전(-3), 3분전(-4)
            price_5m_ago = ohlcv[-6][4]   # 5분전(-6)
            
            # 상승률 계산
            rise_rate_3m = (current_price - price_3m_ago) / price_3m_ago * 100
            rise_rate_5m = (current_price - price_5m_ago) / price_5m_ago * 100
            
            if rise_rate_3m >= 2.0 and rise_rate_5m >= 5.0:
                logger.info(f"🎯 [매수 조건 달성] {ticker} | 3분 상승: {rise_rate_3m:.2f}%, 5분 상승: {rise_rate_5m:.2f}%")
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking buy condition for {ticker}: {e}")
            return False

    def check_sell_condition(self, ticker) -> bool:
        try:
            avg_buy_price, buy_timestamp = self.api.get_last_buy_info(ticker)
            if avg_buy_price <= 0 or buy_timestamp <= 0:
                return False
                
            current_price = self.api.get_current_price(ticker)
            if current_price is None:
                return False
                
            # 수익률 계산
            profit_rate = (current_price - avg_buy_price) / avg_buy_price * 100
            
            # 시간 경과 계산 (time.time()은 초 단위, buy_timestamp는 밀리초 단위)
            elapsed_seconds = (time.time() * 1000 - buy_timestamp) / 1000
            elapsed_hours = elapsed_seconds / 3600
            
            # 1. 10% 이상 익절 또는 10% 이상 손절
            if profit_rate >= 10.0:
                logger.info(f"✨ [익절 조건 달성] {ticker} | 수익률: +{profit_rate:.2f}% (매수가: {avg_buy_price}, 현재가: {current_price})")
                return True
            elif profit_rate <= -5.0:
                logger.info(f"💧 [손절 조건 달성] {ticker} | 손실률: {profit_rate:.2f}% (매수가: {avg_buy_price}, 현재가: {current_price})")
                return True
                
            # 2. 24시간 동안 매도되지 않은 경우 강제 매도 (24시간 = 86400초)
            if elapsed_seconds >= 86400:
                logger.info(f"⏳ [24시간 시간초과 강제 매도] {ticker} | 경과 시간: {elapsed_hours:.1f}시간 | 수익률: {profit_rate:+.2f}%")
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking sell condition for {ticker}: {e}")
            return False
