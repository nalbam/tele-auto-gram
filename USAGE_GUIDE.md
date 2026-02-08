# 사용 가이드 (Usage Guide)

## 시작하기

### 1. 텔레그램 API 키 발급

1. [https://my.telegram.org](https://my.telegram.org) 접속
2. 전화번호로 로그인
3. "API development tools" 클릭
4. 앱 정보 입력 (App title, Short name)
5. API ID와 API Hash 저장

### 2. 봇 설치 및 실행

```bash
# 저장소 클론
git clone https://github.com/nalbam/tele-auto-gram.git
cd tele-auto-gram

# 의존성 설치
pip install -r requirements.txt

# 봇 실행
python main.py
```

### 3. 웹 UI에서 설정

1. 브라우저에서 `http://127.0.0.1:5000` 접속
2. 설정 페이지에서 다음 정보 입력:
   - **API ID**: my.telegram.org에서 발급받은 ID
   - **API Hash**: my.telegram.org에서 발급받은 Hash
   - **전화번호**: 국가코드 포함 (예: +821012345678)
   - **알림 API URL** (선택): 메시지 요약을 받을 API 주소
   - **자동 응답 메시지** (선택): 원하는 응답 메시지

3. "설정 저장" 버튼 클릭

### 4. 텔레그램 인증

첫 실행 시:
1. 터미널에 인증 코드 입력 요청이 표시됩니다
2. 텔레그램으로 받은 인증 코드를 입력하세요
3. 2단계 인증이 설정된 경우, 비밀번호도 입력하세요

## 주요 기능

### 자동 응답
- 누군가 메시지를 보내면 자동으로 응답 메시지 전송
- 기본 메시지: "잠시 후 응답드리겠습니다. 조금만 기다려주세요."
- 웹 UI에서 메시지 변경 가능

### 메시지 기록
- 모든 수신/발신 메시지를 JSON 파일에 저장
- 최근 7일간의 메시지만 보관
- 웹 UI에서 실시간 조회 가능

### 알림 API
- 수신한 메시지를 요약하여 지정된 API로 전송
- POST 요청으로 JSON 데이터 전송
- 선택 사항 (URL을 입력하지 않으면 사용 안 함)

## 환경 변수 설정 (선택사항)

`.env` 파일을 생성하여 설정할 수 있습니다:

```bash
cp .env.example .env
```

`.env` 파일 내용:
```
API_ID=your_api_id
API_HASH=your_api_hash
PHONE=+821012345678
NOTIFY_API_URL=https://your-api.com/notify
AUTO_RESPONSE_MESSAGE=잠시 후 응답드리겠습니다.
```

## 문제 해결

### "설정 필요" 상태가 계속 표시됨
- API ID, API Hash, 전화번호가 모두 입력되었는지 확인
- 웹 UI에서 "설정 저장" 버튼을 눌렀는지 확인

### 인증 코드를 받지 못함
- 전화번호에 국가코드가 포함되었는지 확인 (예: +82)
- 텔레그램 앱에서 로그인된 상태인지 확인

### 메시지 자동 응답이 안 됨
- 터미널에서 봇이 정상 실행 중인지 확인
- "Bot is running..." 메시지가 표시되어야 함
- 인증이 완료되었는지 확인

### 웹 UI가 열리지 않음
- 5000번 포트가 이미 사용 중인지 확인
- 방화벽에서 localhost 접근이 차단되었는지 확인

## 보안 주의사항

⚠️ **중요**: 다음 파일들은 절대 공유하지 마세요!
- `bot_session.session` - 텔레그램 세션 파일
- `data/config.json` - API 키가 저장된 설정 파일
- `.env` - 환경 변수 파일

이 파일들은 `.gitignore`에 포함되어 있어 Git에 커밋되지 않습니다.

## 봇 종료

`Ctrl + C` 키를 눌러 봇을 종료할 수 있습니다.
