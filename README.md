# LMS-Bridge

숭실대 스마트캠퍼스 LMS(`lms.ssu.ac.kr`)의 강의 자료를 **MCP 서버**로 추상화하고,  
**Notion**에는 공지·과제·메타데이터를 동기화하며,  
**Obsidian Vault**는 강의 교안 파일의 로컬 저장소로 활용하는 개인 학습 인프라.

```
LMS (SPA, Playwright)
  └─ LMS Adapter
        ├─ MCP Server  →  Claude / LLM
        ├─ Notion Sync →  공지 · 과제
        └─ Obsidian    →  교안 파일 로컬 저장
```

---

## 빠른 시작

### 1. 환경 설정

```bash
# 의존성 설치 (uv 권장)
uv pip install -e ".[dev]"

# Playwright 브라우저 설치
playwright install chromium

# 환경 변수 설정
cp .env.example .env
# .env 를 열어서 학번, 비밀번호, Notion 토큰 등을 채워주세요
```

### 2. 환경 점검

```bash
python scripts/check_env.py
```

### 3. CLI 사용

```bash
lms-bridge --help
lms-bridge status        # 설정 상태 확인
lms-bridge login         # LMS 로그인 및 세션 캐시 (Phase 1-B)
lms-bridge sync          # Notion / Vault 동기화 (Phase 3-4)
lms-bridge mcp           # MCP 서버 실행 (Phase 2)
```

### 4. 테스트 실행

```bash
pytest                   # 전체 테스트
pytest tests/test_config.py -v
pytest tests/test_models.py -v
```

---

## 개발 로드맵

| 주차 | Phase | 목표 |
|------|-------|------|
| 1주 | 1-A | 프로젝트 셋업 + SSO 로그인 + 강의 목록 파싱 |
| 2주 | 1-B | 강의자료 · 공지 · 과제 파싱 + 단위 테스트 |
| 3주 | 2-A | MCP SDK 셋업 + Tools 정의 |
| 4주 | 2-B | Claude Desktop 연동 + 에러 핸들링 |
| 5주 | 3   | Notion DB 동기화 |
| 6주 | 4   | Obsidian Vault 파일 다운로드 |
| 7주 | 5   | 자동화 · CLI · 문서화 |

---

## 기술 스택

- **언어:** Python 3.11+
- **스크래핑:** Playwright (SPA 대응) + BeautifulSoup4
- **MCP:** `mcp` Python SDK
- **Notion:** `notion-client`
- **설정:** `pydantic-settings` + `.env`
- **로깅:** `loguru`
- **CLI:** `typer` + `rich`
- **스케줄러:** `APScheduler`

---

## 주의사항

- ⚠️ `.env` 파일은 **절대 Git 에 커밋하지 마세요** (자격증명 포함)
- 스마트캠퍼스 LMS 는 매일 **새벽 3시** 데이터 갱신 → 동기화는 **오전 4시 이후** 권장
- LMS 는 SPA 구조 → `httpx` 단독 스크래핑 불가, **Playwright 필수**
