# SSU-LMS-Bridge

숭실대학교 고급AI수학 기말 프로젝트

숭실대 스마트캠퍼스 LMS(`lms.ssu.ac.kr`)의 강의·공지·과제·자료를 가져와
**FastAPI 백엔드 + React 프론트엔드 + LLM 채팅**으로 통합 제공하는 웹 앱.

```
LMS (SSO + Canvas REST API)
   └─ FastAPI Backend
         ├─ /api/courses, /api/assignments, /api/notices
         ├─ /api/chat (litellm: openai / gemini / anthropic)
         └─ /api/sync (APScheduler)
              ↓
         React Frontend (Vite)
```

---

## 디렉터리 구조

```
ssu-lms-bridge/
├── backend/          # FastAPI Python 백엔드
│   ├── app/
│   │   ├── adapter/      # LMS 인증 + Canvas API
│   │   ├── api/routes/   # REST + WebSocket 엔드포인트
│   │   ├── services/     # LLM 등 도메인 서비스
│   │   ├── config.py
│   │   ├── models.py
│   │   └── main.py
│   ├── tests/
│   └── pyproject.toml
├── frontend/         # React + Vite 프론트엔드
│   ├── src/
│   │   ├── api/          # 백엔드 호출 함수
│   │   ├── components/
│   │   ├── pages/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
└── tmp/              # 기존 참고 코드 (gitignored)
```

---

## 빠른 시작

### Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# .env 설정 (LMS_USERNAME, LMS_PASSWORD, LLM_API_KEY 등)
uvicorn app.main:app --reload --port 8000
```

→ `http://localhost:8000/docs` 에서 Swagger UI 확인

### Frontend

```bash
cd frontend
npm install
npm run dev
```

→ `http://localhost:3000` 접속 (`/api`는 자동으로 8000 포트로 프록시)

---

## 개발 로드맵 (3주)

| 주차 | 목표 |
|------|------|
| 1주 | 환경 세팅 · FastAPI 기반 · LMS 인증 · 강의 목록 페이지 |
| 2주 | 과제/공지/자료 라우터 · 강의 상세 페이지 · UI 다듬기 |
| 3주 | LLM 채팅 (WebSocket 스트리밍) · 동기화 스케줄러 · 통합 테스트 |

자세한 일자별 플랜은 Notion **TODO for Week** 페이지 참고.

---

## 기술 스택

**Backend**
- Python 3.11+
- FastAPI + Uvicorn (REST + WebSocket)
- Playwright (LMS SSO 로그인)
- httpx (Canvas REST API 클라이언트)
- litellm (OpenAI / Gemini / Anthropic 멀티 프로바이더)
- pydantic-settings, loguru, APScheduler

**Frontend**
- React 18 + React Router
- Vite (개발 서버 + 번들러)
- JavaScript (TypeScript X)

---

## 주의사항

- ⚠️ `.env` 파일은 **절대 Git 에 커밋하지 마세요** (자격증명 포함)
- 스마트캠퍼스 LMS 는 매일 **새벽 3시** 데이터 갱신 → 동기화는 **오전 4시 이후** 권장
- LMS 는 SPA 구조 → 로그인은 `Playwright` 필수, 이후 데이터 조회는 `canvas.ssu.ac.kr` REST API 활용
