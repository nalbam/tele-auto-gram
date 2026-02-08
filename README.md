# 📱 Telegram Auto-Response Bot (tele-answer-gram)

Telethon을 이용한 텔레그램 자동 응답 봇입니다.

## ✨ 주요 기능

- **자동 응답**: 텔레그램 메시지 수신 시 자동으로 응답 메시지 전송
- **메시지 요약**: 수신한 메시지를 요약하여 지정된 API로 전송
- **메시지 기록**: 수신/발신 메시지를 로컬에 JSON 형태로 저장 (최근 7일)
- **웹 UI**: 깔끔하고 모던한 디자인의 관리 인터페이스
- **간편한 설정**: 웹 UI를 통한 API 키 및 환경설정

## 🚀 시작하기

### 사전 요구사항

- Python 3.7 이상
- 텔레그램 계정
- API ID와 API Hash ([my.telegram.org](https://my.telegram.org)에서 발급)

### 설치

1. 저장소 클론:
```bash
git clone https://github.com/nalbam/tele-answer-gram.git
cd tele-answer-gram
```

2. 의존성 설치:
```bash
pip install -r requirements.txt
```

### 실행

```bash
python main.py
```

실행 후 브라우저에서 `http://127.0.0.1:5000`으로 접속하세요.

## ⚙️ 설정

### 웹 UI를 통한 설정

1. `http://127.0.0.1:5000` 접속
2. 다음 정보 입력:
   - **API ID**: my.telegram.org에서 발급받은 API ID
   - **API Hash**: my.telegram.org에서 발급받은 API Hash
   - **전화번호**: 국가코드를 포함한 전화번호 (예: +821012345678)
   - **알림 API URL** (선택): 메시지 요약을 전송할 외부 API 주소
   - **자동 응답 메시지** (선택): 기본 메시지 변경 가능

### 환경 변수를 통한 설정 (선택사항)

`.env` 파일을 생성하여 설정할 수도 있습니다:

```env
API_ID=your_api_id
API_HASH=your_api_hash
PHONE=+821012345678
NOTIFY_API_URL=https://your-api.com/notify
AUTO_RESPONSE_MESSAGE=잠시 후 응답드리겠습니다.
```

## 📖 사용 방법

1. **첫 실행시**: 웹 UI에서 설정 정보를 입력하고 저장
2. **봇 인증**: 처음 실행하면 텔레그램으로 인증 코드가 전송됨
3. **자동 응답**: 설정 완료 후 받은 메시지에 자동으로 응답
4. **메시지 확인**: 웹 UI에서 최근 메시지 내역 조회

## 📁 프로젝트 구조

```
tele-answer-gram/
├── main.py              # 메인 실행 파일
├── bot.py               # 텔레그램 봇 로직
├── web.py               # 웹 UI 서버
├── config.py            # 설정 관리
├── storage.py           # 메시지 저장 관리
├── utils.py             # 유틸리티 함수
├── requirements.txt     # 의존성 목록
├── templates/
│   └── index.html      # 웹 UI 템플릿
└── data/               # 데이터 저장 디렉토리 (자동 생성)
    ├── config.json     # 설정 파일
    └── messages.json   # 메시지 기록
```

## 🔔 알림 API

외부 API로 메시지 요약을 전송하려면 다음 형식의 JSON을 받을 수 있는 엔드포인트를 준비하세요:

```json
{
  "timestamp": "2024-01-01T12:00:00",
  "sender": "User Name",
  "summary": "메시지 요약 내용"
}
```

## 📝 메시지 저장

메시지는 `data/messages.json` 파일에 저장되며, 다음 형식을 따릅니다:

```json
[
  {
    "timestamp": "2024-01-01T12:00:00",
    "direction": "received",
    "sender": "User Name",
    "text": "메시지 내용",
    "summary": "요약"
  }
]
```

자동으로 7일이 지난 메시지는 삭제됩니다.

## 🛡️ 보안

- 이 봇은 localhost(127.0.0.1)에서만 실행되도록 설계되었습니다
- API 키와 세션 파일은 절대 공유하지 마세요
- `.gitignore`에 민감한 파일들이 포함되어 있습니다

## 📄 라이선스

MIT License

## 🤝 기여

이슈와 풀 리퀘스트는 언제나 환영합니다!