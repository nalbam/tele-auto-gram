# 📱 TeleAutoGram

Telethon 기반 텔레그램 자동 응답 봇입니다. 웹 UI를 통해 설정과 인증을 관리하고, 프라이빗 메시지에 자동으로 응답합니다.

## ✨ 주요 기능

- **자동 응답**: 텔레그램 메시지 수신 시 자동으로 응답 메시지 전송
- **AI 응답**: OpenAI API를 이용한 지능형 자동 응답 (선택사항)
- **웹 UI 인증**: 웹 브라우저에서 Telegram 인증 코드 및 2FA 비밀번호 입력
- **메시지 기록**: 수신/발신 메시지를 로컬에 JSON 형태로 저장 (최근 7일)
- **웹 UI**: 모던한 관리 인터페이스 (설정, 인증, 대화 목록)
- **Docker 지원**: 비대화형 환경에서도 웹 UI를 통한 인증 가능

## 🚀 시작하기

### 사전 요구사항

- Python 3.7 이상 또는 Docker
- 텔레그램 계정
- API ID와 API Hash ([my.telegram.org](https://my.telegram.org)에서 발급)

### 방법 1: Docker 사용 (권장)

1. Docker 이미지 가져오기:
```bash
docker pull ghcr.io/nalbam/tele-auto-gram:latest
```

2. 환경 변수 설정:
```bash
cp .env.example .env
# .env 파일 편집하여 API_ID, API_HASH, PHONE 설정
```

3. Docker Compose로 실행:
```bash
docker-compose up -d
```

또는 Docker 직접 실행:
```bash
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e API_ID=your_api_id \
  -e API_HASH=your_api_hash \
  -e PHONE=+821012345678 \
  --name tele-auto-gram \
  ghcr.io/nalbam/tele-auto-gram:latest
```

### 방법 2: Python으로 직접 실행

1. 저장소 클론:
```bash
git clone https://github.com/nalbam/tele-auto-gram.git
cd tele-auto-gram
```

2. 의존성 설치:
```bash
pip install -r requirements.txt
```

3. 실행:
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
   - **자동 응답 메시지** (선택): AI 미설정 시 사용되는 기본 응답 메시지
   - **OpenAI API Key** (선택): AI 자동 응답 활성화
   - **OpenAI Model** (선택): 사용할 모델 (기본: gpt-4o-mini)
   - **시스템 프롬프트** (선택): AI 응답 성향 설정

### 환경 변수를 통한 설정 (선택사항)

`.env` 파일을 생성하여 설정할 수도 있습니다:

```conf
API_ID=your_api_id
API_HASH=your_api_hash
PHONE=+821012345678
AUTO_RESPONSE_MESSAGE=잠시 후 응답드리겠습니다.
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
SYSTEM_PROMPT=
LOG_LEVEL=INFO
```

## 📖 사용 방법

1. **설정**: 웹 UI(설정 탭)에서 API ID, API Hash, 전화번호 입력 후 저장
2. **서버 재시작**: 설정 저장 후 서버 재시작
3. **인증**: 웹 UI(인증 탭)에서 Telegram 인증 코드 입력 (2FA 설정 시 비밀번호도 입력)
4. **자동 응답**: 인증 완료 후 받은 프라이빗 메시지에 자동으로 응답
5. **메시지 확인**: 웹 UI(대화 목록 탭)에서 최근 메시지 내역 조회

## 📁 프로젝트 구조

```
tele-auto-gram/
├── main.py              # 메인 실행 파일 (Flask + 봇 스레드 시작)
├── bot.py               # 텔레그램 봇 로직 (인증 흐름 + 메시지 핸들러)
├── web.py               # 웹 UI 서버 (설정/인증/메시지 API)
├── ai.py                # AI 응답 생성 (OpenAI)
├── config.py            # 설정 관리
├── storage.py           # 메시지 저장 관리
├── requirements.txt     # 의존성 목록
├── .env.example         # 환경 변수 예제
├── Dockerfile           # Docker 이미지 빌드 설정
├── docker-compose.yml   # Docker Compose 설정
├── templates/
│   └── index.html      # 웹 UI 템플릿
├── docs/
│   └── USAGE_GUIDE.md  # 사용 가이드 및 문제 해결
├── .github/workflows/
│   └── docker-build.yml # CI/CD 자동 이미지 빌드
└── data/               # 데이터 저장 디렉토리 (자동 생성, Docker 볼륨 마운트 대상)
    ├── config.json     # 설정 파일
    ├── messages.json   # 메시지 기록
    └── bot_session.session  # Telethon 세션 파일
```

## 🐳 Docker 이미지

### 사용 가능한 태그

Docker 이미지는 GitHub Actions를 통해 자동으로 빌드되며 GitHub Container Registry에 게시됩니다:

- `ghcr.io/nalbam/tele-auto-gram:latest` - 최신 릴리스
- `ghcr.io/nalbam/tele-auto-gram:1` - 메이저 버전 1.x.x
- `ghcr.io/nalbam/tele-auto-gram:1.0` - 마이너 버전 1.0.x
- `ghcr.io/nalbam/tele-auto-gram:1.0.0` - 특정 버전
- `ghcr.io/nalbam/tele-auto-gram:sha-xxxxxxx` - 커밋 SHA

### 버전 태깅

새 버전을 릴리스하려면 `v1.x.x` 형식의 Git 태그를 생성하세요:

```bash
git tag v1.0.0
git push origin v1.0.0
```

태그가 푸시되면 GitHub Actions가 자동으로 Docker 이미지를 빌드하고 GitHub Container Registry에 푸시합니다.

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
