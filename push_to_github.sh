#!/bin/bash
echo "🚀 깃허브 업로드를 시작합니다..."

# 기존 깃 설정이 있다면 무시하고 진행
git init

# 파일 추가 (.gitignore가 작동하여 API 키는 제외됨)
git add .

# 커밋
git commit -m "🚀 Initial commit: Binance Auto Trading Bot"

# 메인 브랜치 설정
git branch -M main

# 리모트 주소 연동 (에러 무시 처리)
git remote add origin https://github.com/Lissung/AutoTrading_Crypto.git 2>/dev/null || git remote set-url origin https://github.com/Lissung/AutoTrading_Crypto.git

# 깃허브로 푸시
git push -u origin main

echo "✅ 깃허브 업로드가 완료되었습니다! (에러가 났다면 깃허브 로그인 권한 문제일 수 있습니다.)"
