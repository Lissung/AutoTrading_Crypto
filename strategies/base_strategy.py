from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    def __init__(self, api_client):
        self.api = api_client
        
    @abstractmethod
    def check_buy_condition(self, ticker) -> bool:
        """
        매수 조건을 검사합니다.
        True를 반환하면 매수를 진행합니다.
        """
        pass
        
    @abstractmethod
    def check_sell_condition(self, ticker) -> bool:
        """
        매도(익절/손절) 조건을 검사합니다.
        True를 반환하면 매도를 진행합니다.
        """
        pass
