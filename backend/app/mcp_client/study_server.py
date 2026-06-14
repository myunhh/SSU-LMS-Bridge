"""학습 도우미 adapter 를 in-process MCP 서버로 노출 (study__*).

설계
----
LMS MCP(lms_server.py)와 동일한 "토큰 없는 항상-마운트" 패턴의 2번째 사례다:
  (a) 토큰/인증이 필요 없으니 setup.py 에서 **무조건 마운트**하고,
      deps.py:_build_registry 도 무조건 등록한다 (마운트↔등록 두 조건이 짝).
  (b) 세션·외부 의존이 전혀 없다 — 저장소는 로컬 JSON 파일 2종(quizzes.json /
      decks.json)뿐이라 lms_server 의 `_client_cm`(CanvasClient 라이프사이클)이
      필요 없고, 디스패치가 곧장 파일 IO 를 한다.

역할 분담 (확정사항)
--------------------
이 MCP 는 **저장 / 조회 / 복습(SRS)** 의 결정적 도구만 제공한다. 퀴즈 문항·
플래시카드의 *생성* 은 채팅 LLM 책임이다 — LLM 이 lms__list_notices /
list_assignments 로 본문을 읽어 문항을 만든 뒤 study__save_quiz / save_deck 로
저장만 한다. 따라서 이 모듈은 litellm 을 import 하지 않으며, MCP 안에서 LLM 을
재호출하지 않는다.

저장소
------
- 기본 루트: `settings.root_dir / ".cache" / "study"` (CWD 무관 절대경로 —
  vault_service.MANIFEST_PATH 와 동일 규약). 경로는 모듈 레벨 `_store_dir()` 로
  노출해 테스트가 tmp_path 로 monkeypatch 할 수 있다(connectors._env_path 패턴).
- 파일 손상에 관대: 단일 사용자 로컬 캐시라 깨진 JSON 은 빈 컨테이너로 폴백한다.
- 저장은 tmp → os.replace 원자적 교체(부분 손상 방지, connectors._upsert_env_file 동일).

테스트 용이성
-------------
SSE/Server 내부 구조에 의존하지 않고 100% 오프라인 단위 테스트가 가능하도록,
디스패치 로직을 모듈 레벨 `_dispatch(name, arguments)` 로 분리하고 factory 의
@server.call_tool() 가 거기에 위임한다. `_dump`(순수) 도 모듈 레벨에 노출한다.
시간 의존(due 계산)은 save_deck/list_decks/review_due/grade_card 의 `now` 인자로
주입할 수 있어 테스트가 시계에 묶이지 않는다.
"""
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent, Tool

from app.config import settings

# ── SRS(SM-2 경량) 상수 ──────────────────────────────────────
EASE_DEFAULT = 2.5
EASE_MIN = 1.3
EASE_BONUS = 0.1     # 정답 시 ease 증가
EASE_PENALTY = 0.2   # 오답 시 ease 감소


# ── 저장 경로 (테스트에서 monkeypatch 대상) ─────────────────
def _store_dir() -> Path:
    """학습 데이터 저장 디렉터리 — root_dir/.cache/study 절대경로.

    connectors._env_path() 와 같은 이유로 모듈 레벨 함수로 분리한다 — 테스트가
    `monkeypatch.setattr(study_server, "_store_dir", lambda: tmp_path/"study")`
    로 격리할 수 있게(실 .cache/study 를 절대 건드리지 않음).
    """
    return settings.root_dir / ".cache" / "study"


def _quizzes_path() -> Path:
    return _store_dir() / "quizzes.json"


def _decks_path() -> Path:
    return _store_dir() / "decks.json"


# ── 저장 헬퍼 (순수에 가깝게) ────────────────────────────────
def _load(path: Path, key: str) -> dict:
    """파일 → dict. 없거나 JSON 깨지면 빈 컨테이너({key: []}) 폴백.

    단일 사용자 로컬 캐시라 손상에 관대하게(예외로 죽지 않게) 처리한다.
    """
    if not path.exists():
        return {key: []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {key: []}
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        return {key: []}
    return data


def _save(path: Path, data: dict) -> None:
    """tmp → os.replace 원자적 교체 (부분 손상 방지, connectors._upsert_env_file 동일)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _dump(data) -> str:
    """dict/list → JSON 문자열. LLM 소비용이라 ensure_ascii=False 로 한글 유지."""
    return json.dumps(data, ensure_ascii=False, default=str)


def _new_id(prefix: str) -> str:
    """'<prefix>_' + uuid4 hex8 (예: 'q_8f3c1a2b'). 충돌 사실상 0."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    """현재 UTC ISO 문자열 (Z 표기). now 인자 미지정 시 fallback."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    """ISO 문자열 → tz-aware UTC datetime. 'Z' / 오프셋 / naive 모두 허용."""
    s = (value or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iso(dt: datetime) -> str:
    """datetime → 'YYYY-MM-DDTHH:MM:SSZ' (UTC 정규화)."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── SRS 순수 함수 (SM-2 경량) ────────────────────────────────
def _apply_review(card: dict, correct: bool, now: datetime) -> dict:
    """복습 결과 1건을 SM-2 경량 공식으로 반영해 card 를 in-place 갱신 후 반환.

    now 를 인자로 받아 시간 비결정성을 제거한다 — 같은 입력·같은 now 면 같은 출력
    (단위 테스트가 정확한 due/interval/ease 값을 단언 가능).

    [정답] reps+=1; reps==1→interval=1, ==2→3, 그 이상→round(interval*ease);
           ease += 0.1
    [오답] reps=0; interval=1; ease = max(1.3, ease-0.2)
    [공통] ease 하한 1.3 클램프; due = now + interval일; last_reviewed = now
    """
    ease = float(card.get("ease", EASE_DEFAULT))
    interval = int(card.get("interval", 0))
    reps = int(card.get("reps", 0))

    if correct:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 3  # SM-2 의 6일을 학기용으로 단축
        else:
            interval = round(interval * ease)
        ease = ease + EASE_BONUS
    else:
        reps = 0
        interval = 1
        ease = ease - EASE_PENALTY

    ease = max(EASE_MIN, ease)

    card["ease"] = ease
    card["interval"] = interval
    card["reps"] = reps
    card["due"] = _iso(now + timedelta(days=interval))
    card["last_reviewed"] = _iso(now)
    return card


# ── 디스패치 헬퍼 ────────────────────────────────────────────
def _quiz_meta(q: dict) -> dict:
    """목록용 가벼운 퀴즈 메타(본문 questions 제외, question_count 포함)."""
    return {
        "id": q.get("id"),
        "title": q.get("title"),
        "question_count": len(q.get("questions", [])),
        "source": q.get("source"),
        "created_at": q.get("created_at"),
        "updated_at": q.get("updated_at"),
    }


def _new_card(raw: dict, now: datetime) -> dict:
    """입력 카드 → SRS 상태 초기화한 카드 레코드 (due=now, ease=2.5, interval=0)."""
    return {
        "id": _new_id("c"),
        "front": raw.get("front", ""),
        "back": raw.get("back", ""),
        "hint": raw.get("hint", "") or "",
        "ease": EASE_DEFAULT,
        "interval": 0,
        "reps": 0,
        "due": _iso(now),  # 신규 카드는 즉시 복습 대상
        "last_reviewed": None,
    }


def _save_quiz(arguments: dict) -> dict:
    title = arguments.get("title")
    questions = arguments.get("questions")
    if not title:
        raise ValueError("title 은 필수입니다.")
    if not questions or not isinstance(questions, list):
        raise ValueError("questions 는 1개 이상이어야 합니다.")

    now = _now_iso()
    data = _load(_quizzes_path(), "quizzes")
    quizzes = data["quizzes"]

    qid = (arguments.get("id") or "").strip() or _new_id("q")
    record = {
        "id": qid,
        "title": title,
        "source": arguments.get("source"),
        "questions": questions,
        "created_at": now,
        "updated_at": now,
    }

    # upsert: 같은 id 있으면 덮어쓰기(created_at 보존), 없으면 추가
    for i, existing in enumerate(quizzes):
        if existing.get("id") == qid:
            record["created_at"] = existing.get("created_at", now)
            quizzes[i] = record
            break
    else:
        quizzes.append(record)

    _save(_quizzes_path(), data)
    return {"ok": True, "id": qid, "title": title, "question_count": len(questions)}


def _list_quizzes(arguments: dict) -> dict:
    course = (arguments.get("course") or "").strip()
    limit = int(arguments.get("limit", 50))
    quizzes = _load(_quizzes_path(), "quizzes")["quizzes"]
    if course:
        quizzes = [
            q for q in quizzes
            if course in str((q.get("source") or {}).get("course", ""))
        ]
    return {"quizzes": [_quiz_meta(q) for q in quizzes[:limit]]}


def _get_quiz(arguments: dict) -> dict:
    qid = arguments.get("id")
    if not qid:
        raise ValueError("id 는 필수입니다.")
    for q in _load(_quizzes_path(), "quizzes")["quizzes"]:
        if q.get("id") == qid:
            return {"quiz": q}
    raise ValueError(f"퀴즈 없음: {qid}")


def _delete_quiz(arguments: dict) -> dict:
    qid = arguments.get("id")
    if not qid:
        raise ValueError("id 는 필수입니다.")
    data = _load(_quizzes_path(), "quizzes")
    before = len(data["quizzes"])
    data["quizzes"] = [q for q in data["quizzes"] if q.get("id") != qid]
    if len(data["quizzes"]) == before:
        return {"ok": False, "deleted": None}  # 멱등 — 없어도 예외 안 냄
    _save(_quizzes_path(), data)
    return {"ok": True, "deleted": qid}


def _save_deck(arguments: dict) -> dict:
    title = arguments.get("title")
    cards = arguments.get("cards")
    if not title:
        raise ValueError("title 은 필수입니다.")
    if not cards or not isinstance(cards, list):
        raise ValueError("cards 는 1개 이상이어야 합니다.")

    now_dt = _parse_iso(arguments.get("now") or _now_iso())
    now = _iso(now_dt)
    data = _load(_decks_path(), "decks")
    decks = data["decks"]

    did = (arguments.get("id") or "").strip() or _new_id("d")

    # 기존 덱이면 동일 front+back 카드의 SRS 상태를 보존(복습 진척 유실 방지).
    # ⚠️ (front,back) 가 같은 카드가 2장 이상이면 1:1 로 짝지어야 한다 — dict 단일
    # 값으로 두면 같은 card_id 로 붕괴해 둘째 카드가 영원히 due 로 남고 review_due 에
    # 중복 노출된다(#1). 키→리스트로 모아 앞에서부터 소진(pop(0))해 1:1 매칭한다.
    existing_deck = next((d for d in decks if d.get("id") == did), None)
    preserved: dict[tuple, list[dict]] = {}
    if existing_deck:
        for c in existing_deck.get("cards", []):
            preserved.setdefault((c.get("front"), c.get("back")), []).append(c)

    new_cards = []
    for raw in cards:
        key = (raw.get("front", ""), raw.get("back", ""))
        bucket = preserved.get(key)
        if bucket:
            # 기존 SRS 상태 보존(소진), front/back/hint 는 새 입력으로 갱신
            kept = dict(bucket.pop(0))
            kept["front"] = raw.get("front", "")
            kept["back"] = raw.get("back", "")
            kept["hint"] = raw.get("hint", kept.get("hint", "")) or ""
            new_cards.append(kept)
        else:
            new_cards.append(_new_card(raw, now_dt))

    # 방어선 2: 조립 후 card_id 중복이 남으면(예: 과거 손상 덱) 새 id 로 재발급해
    # SRS 상태머신이 항상 1 카드 = 1 card_id 불변식을 지키게 한다.
    seen_ids: set[str] = set()
    for card in new_cards:
        cid = card.get("id")
        if cid in seen_ids:
            card["id"] = _new_id("c")
        seen_ids.add(card["id"])

    record = {
        "id": did,
        "title": title,
        "source": arguments.get("source"),
        "created_at": existing_deck.get("created_at", now) if existing_deck else now,
        "updated_at": now,
        "cards": new_cards,
    }

    if existing_deck:
        decks[decks.index(existing_deck)] = record
    else:
        decks.append(record)

    _save(_decks_path(), data)
    return {"ok": True, "id": did, "title": title, "card_count": len(new_cards)}


def _list_decks(arguments: dict) -> dict:
    now_dt = _parse_iso(arguments.get("now") or _now_iso())
    course = (arguments.get("course") or "").strip()
    decks = _load(_decks_path(), "decks")["decks"]
    if course:
        decks = [
            d for d in decks
            if course in str((d.get("source") or {}).get("course", ""))
        ]
    out = []
    for d in decks:
        cards = d.get("cards", [])
        due_count = sum(1 for c in cards if _parse_iso(c.get("due", "")) <= now_dt)
        out.append({
            "id": d.get("id"),
            "title": d.get("title"),
            "card_count": len(cards),
            "due_count": due_count,
            "source": d.get("source"),
            "created_at": d.get("created_at"),
        })
    return {"decks": out}


def _review_due(arguments: dict) -> dict:
    now_dt = _parse_iso(arguments.get("now") or _now_iso())
    deck_id = (arguments.get("deck_id") or "").strip()
    limit = int(arguments.get("limit", 20))
    decks = _load(_decks_path(), "decks")["decks"]

    due_cards = []
    for d in decks:
        if deck_id and d.get("id") != deck_id:
            continue
        for c in d.get("cards", []):
            if _parse_iso(c.get("due", "")) <= now_dt:
                due_cards.append({
                    "deck_id": d.get("id"),
                    "deck_title": d.get("title"),
                    "card_id": c.get("id"),
                    "front": c.get("front"),
                    "back": c.get("back"),
                    "hint": c.get("hint", ""),
                    "due": c.get("due"),
                    "interval": c.get("interval", 0),
                    "reps": c.get("reps", 0),
                })
    # 결정적 정렬: due 오름차순, 동률은 card_id
    due_cards.sort(key=lambda x: (x["due"] or "", x["card_id"] or ""))
    return {"cards": due_cards[:limit]}


def _grade_card(arguments: dict) -> dict:
    deck_id = arguments.get("deck_id")
    card_id = arguments.get("card_id")
    if not deck_id or not card_id:
        raise ValueError("deck_id, card_id 는 필수입니다.")
    correct = bool(arguments.get("correct"))
    now_dt = _parse_iso(arguments.get("now") or _now_iso())

    data = _load(_decks_path(), "decks")
    deck = next((d for d in data["decks"] if d.get("id") == deck_id), None)
    if deck is None:
        raise ValueError(f"덱 없음: {deck_id}")
    card = next((c for c in deck.get("cards", []) if c.get("id") == card_id), None)
    if card is None:
        raise ValueError(f"카드 없음: {card_id}")

    _apply_review(card, correct, now_dt)
    deck["updated_at"] = _iso(now_dt)
    _save(_decks_path(), data)
    return {
        "ok": True,
        "card_id": card_id,
        "correct": correct,
        "ease": card["ease"],
        "interval": card["interval"],
        "reps": card["reps"],
        "due": card["due"],
    }


async def _dispatch(name: str, arguments: dict) -> list[TextContent]:
    """tool 이름별 디스패치 (factory 의 call_tool 데코레이터가 위임).

    각 핸들러는 dict 를 반환하고 여기서 _dump → TextContent 로 감싼다.
    파일 IO 만 하므로 본질은 동기지만, MCP @call_tool 핸들러·테스트가 await 하는
    lms_server 와 동일한 호출 규약을 맞추기 위해 async 로 둔다.
    ValueError(필수 인자 누락·없는 id 등)는 가드하지 않고 전파 → base.py 가
    RuntimeError 로 변환 → LLM tool_result(ERROR ...) (lms_server 와 동일 정책).
    """
    arguments = arguments or {}

    if name == "save_quiz":
        result = _save_quiz(arguments)
    elif name == "list_quizzes":
        result = _list_quizzes(arguments)
    elif name == "get_quiz":
        result = _get_quiz(arguments)
    elif name == "delete_quiz":
        result = _delete_quiz(arguments)
    elif name == "save_deck":
        result = _save_deck(arguments)
    elif name == "list_decks":
        result = _list_decks(arguments)
    elif name == "review_due":
        result = _review_due(arguments)
    elif name == "grade_card":
        result = _grade_card(arguments)
    else:
        # 알 수 없는 tool — None 반환 시 SDK 가 'Unexpected return type' 오류를
        # 내므로 명시적으로 거부한다 (lms/notion/obsidian_server 와 동일 정책).
        raise ValueError(f"unknown tool: {name}")

    return [TextContent(type="text", text=_dump(result))]


# ── inputSchema 단편 ─────────────────────────────────────────
_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "q": {"type": "string", "description": "문제 본문"},
        "type": {"type": "string", "enum": ["mcq", "short", "tf"], "description": "객관식/단답/참거짓 (기본 mcq)"},
        "choices": {"type": "array", "items": {"type": "string"}, "description": "type=mcq 일 때 보기"},
        "answer": {"type": "string", "description": "정답(문자열)"},
        "explanation": {"type": "string", "description": "해설(선택)"},
    },
    "required": ["q", "answer"],
}

_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "front": {"type": "string", "description": "앞면(질문/용어)"},
        "back": {"type": "string", "description": "뒷면(답/설명)"},
        "hint": {"type": "string", "description": "힌트(선택)"},
    },
    "required": ["front", "back"],
}

_SOURCE_SCHEMA = {
    "type": "object",
    "description": "출처 메타(선택) — lms 본문에서 만들었음을 추적",
    "properties": {
        "kind": {"type": "string", "enum": ["notice", "assignment", "manual"]},
        "course": {"type": "string"},
        "ref_id": {"type": "integer"},
    },
}


def create_study_mcp_server() -> Server:
    """학습 도우미(퀴즈·플래시카드 SRS) MCP 서버 생성.

    토큰/세션이 필요 없어 setup.py 가 무조건 마운트하고 deps 도 무조건 등록한다.
    """
    server = Server("study-mcp")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="save_quiz",
                description=(
                    "퀴즈 생성/갱신(upsert). 문항은 네(LLM)가 lms__list_notices/"
                    "list_assignments 본문을 읽어 만들어 그대로 저장만 한다. id 주면 "
                    "덮어쓰기, 없으면 신규. 반환: {ok,id,title,question_count}."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "questions": {"type": "array", "items": _QUESTION_SCHEMA},
                        "id": {"type": "string", "description": "갱신 시 기존 퀴즈 id"},
                        "source": _SOURCE_SCHEMA,
                    },
                    "required": ["title", "questions"],
                },
            ),
            Tool(
                name="list_quizzes",
                description=(
                    "저장된 퀴즈 메타 목록(본문 questions 제외 — 토큰 절약). "
                    "course 로 과목 필터(source.course 부분일치). 전체 문항은 get_quiz."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "course": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                    },
                },
            ),
            Tool(
                name="get_quiz",
                description="id 로 퀴즈 전체(문항·정답·해설 포함) 조회. 채점/재출제용.",
                inputSchema={
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
            ),
            Tool(
                name="delete_quiz",
                description="id 로 퀴즈 삭제(멱등 — 없어도 예외 없이 ok:false).",
                inputSchema={
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
            ),
            Tool(
                name="save_deck",
                description=(
                    "플래시카드 덱 생성/갱신. 카드별 SRS 상태(ease=2.5,interval=0,"
                    "due=now)를 자동 부여. 같은 덱 id 갱신 시 동일 front+back 카드는 "
                    "기존 SRS 상태 보존(복습 진척 유실 방지)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "cards": {"type": "array", "items": _CARD_SCHEMA},
                        "id": {"type": "string", "description": "갱신 시 기존 덱 id"},
                        "source": _SOURCE_SCHEMA,
                        "now": {"type": "string", "description": "due 기준 시각(ISO, 주입용)"},
                    },
                    "required": ["title", "cards"],
                },
            ),
            Tool(
                name="list_decks",
                description=(
                    "덱 메타 목록 + 각 덱의 '지금 복습 대상(due<=now)' 카드 수(due_count). "
                    "course 로 필터. now 미지정 시 현재 UTC."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "course": {"type": "string"},
                        "now": {"type": "string", "description": "기준 시각(ISO, 주입용)"},
                    },
                },
            ),
            Tool(
                name="review_due",
                description=(
                    "due<=now 인 복습 대상 카드만 due 오름차순으로 반환(자가채점용, "
                    "back 포함). deck_id 주면 그 덱만. now 주입으로 테스트 시간 독립."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "deck_id": {"type": "string", "description": "생략 시 전 덱"},
                        "now": {"type": "string", "description": "기준 시각(ISO, 주입용)"},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            ),
            Tool(
                name="grade_card",
                description=(
                    "복습 결과 1건 반영 → SM-2 경량 공식으로 ease/interval/reps/due "
                    "재계산 후 저장. correct=false 면 reps=0·interval=1 리셋. "
                    "반환: 갱신된 SRS 상태."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "deck_id": {"type": "string"},
                        "card_id": {"type": "string"},
                        "correct": {"type": "boolean"},
                        "now": {"type": "string", "description": "due 계산 시각(ISO, 주입용)"},
                    },
                    "required": ["deck_id", "card_id", "correct"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        return await _dispatch(name, arguments)

    return server
