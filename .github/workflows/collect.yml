name: 신용거래융자 데이터 수집

on:
  schedule:
    - cron: '0 9 * * 1-6'   # UTC 09:00 = KST 18:00, 월~토
  workflow_dispatch:

# keepalive 커밋을 푸시하기 위한 쓰기 권한
permissions:
  contents: write

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Python 설치
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 패키지 설치
        run: pip install -r requirements.txt

      - name: 데이터 수집 실행
        run: python collect.py
        env:
          DATA_GO_KR_KEY: ${{ secrets.DATA_GO_KR_KEY }}
          SUPABASE_URL:   ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY:   ${{ secrets.SUPABASE_KEY }}

      # GitHub는 60일간 커밋이 없는 공개 저장소의 예약 실행을 자동으로 끔.
      # 마지막 커밋이 45일 이상 지났을 때만 작은 기록 파일을 커밋해서 활성 상태를 유지.
      # (수집이 실패한 날에도 실행되도록 always())
      - name: 저장소 활성 상태 유지 (60일 자동 중지 방지)
        if: always()
        run: |
          last=$(git log -1 --format=%ct)
          now=$(date +%s)
          days=$(( (now - last) / 86400 ))
          echo "마지막 커밋 후 ${days}일 경과"
          if [ "$days" -ge 45 ]; then
            date -u +"%Y-%m-%dT%H:%M:%SZ" > .github/keepalive.txt
            git config user.name  "github-actions[bot]"
            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
            git add .github/keepalive.txt
            git commit -m "keepalive: 예약 실행 유지용 자동 커밋"
            git push
            echo "keepalive 커밋 완료"
          else
            echo "커밋 불필요"
          fi
