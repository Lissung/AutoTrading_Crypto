import logging
import os
from datetime import datetime

def setup_logger():
    # 로그 디렉토리 생성
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 오늘 날짜로 로그 파일 이름 지정
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f'trading_bot_{date_str}.log')
    
    # 로거 설정
    logger = logging.getLogger('AutoTradingBot')
    logger.setLevel(logging.INFO)
    
    # 핸들러가 이미 추가되어 있다면 중복 추가 방지
    if not logger.handlers:
        # 파일 출력용 핸들러
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        file_handler.setFormatter(file_formatter)
        
        # 콘솔 출력용 핸들러
        stream_handler = logging.StreamHandler()
        stream_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        stream_handler.setFormatter(stream_formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        
    return logger

logger = setup_logger()
