"""세션 파일 저장 회귀 테스트 (오프라인).

두 가지 회귀를 방지한다:

1. 권한 (#기존) — _save_session() 이 기본 umask(보통 0644 = 전체 읽기 가능)로
   세션 파일을 만들어 SSO 쿠키·xn_api_token 이 다른 로컬 사용자에게 노출되던 문제:
     - 신규 저장 시 0600(소유자 전용)으로 생성
     - 이미 0644 로 존재하던 파일도 재저장 시 0600 으로 좁아짐 (load_session 갱신 경로)

2. 원자성 (#13) — _save_session() 이 O_TRUNC 로 본 파일을 제자리에서 덮어쓰다가
   쓰기 도중 중단/직렬화 실패 시 세션 파일이 반쯤 잘려 손상되고, 직전 유효 세션마저
   날아가던 문제. 이제 tmp 파일에 0600 으로 먼저 쓴 뒤 os.replace 로 원자 교체하므로:
     - 직렬화/쓰기 실패 시 직전 유효 세션 파일이 그대로 보존됨
     - 실패해도 tmp 잔여물(.json.tmp)이 남지 않음
     - tmp 도 처음부터 0600 으로 생성 (시크릿이 잠깐도 0644 로 노출되지 않음)

Playwright 실구동 금지 — _save_session 은 순수 파일 쓰기이므로 직접 호출한다.
"""
import json
import os
import stat

import pytest

from app.adapter.auth import SSULMSAuthPlaywright


def _file_mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_save_session_creates_file_with_0600(tmp_path):
    """신규 세션 파일은 처음부터 소유자 전용(0600)으로 생성된다."""
    session_file = tmp_path / "session_state.json"
    auth = SSULMSAuthPlaywright(session_file=str(session_file))

    auth._save_session([], {})

    assert session_file.exists()
    assert _file_mode(session_file) == 0o600

    # 내용도 정상 JSON 으로 저장됐는지 (권한 변경이 쓰기를 깨지 않았는지)
    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert data["cookies"] == []
    assert data["storage_state"] == {}
    assert "saved_at" in data


def test_save_session_narrows_existing_0644_file(tmp_path):
    """기존에 0644 로 존재하던 파일도 재저장(세션 갱신) 시 0600 으로 좁아진다."""
    session_file = tmp_path / "session_state.json"
    session_file.write_text("{}", encoding="utf-8")
    session_file.chmod(0o644)
    assert _file_mode(session_file) == 0o644  # 전제 확인

    auth = SSULMSAuthPlaywright(session_file=str(session_file))
    auth._save_session([{"name": "c", "value": "v"}], {"origins": []})

    assert _file_mode(session_file) == 0o600
    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert data["cookies"] == [{"name": "c", "value": "v"}]


def test_save_session_leaves_no_tmp_file_on_success(tmp_path):
    """정상 저장 후 tmp 잔여물(.json.tmp)이 남지 않는다 (os.replace 로 소비됨)."""
    session_file = tmp_path / "session_state.json"
    auth = SSULMSAuthPlaywright(session_file=str(session_file))

    auth._save_session([], {})

    assert session_file.exists()
    # tmp_path 안에 본 파일 외 잔여 .tmp 가 없어야 한다
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != session_file.name]
    assert leftovers == []


def test_save_session_atomic_preserves_prior_session_on_failure(tmp_path, monkeypatch):
    """직렬화 실패(쓰기 도중 중단 모사) 시 직전 유효 세션 파일이 그대로 보존된다.

    O_TRUNC 제자리 덮어쓰기였다면 본 파일이 이미 비워진 뒤 실패해 직전 세션이
    날아갔다. tmp→os.replace 라 본 파일은 교체 직전까지 무손상으로 남는다.
    """
    session_file = tmp_path / "session_state.json"
    auth = SSULMSAuthPlaywright(session_file=str(session_file))

    # 1) 직전 유효 세션을 한 번 정상 저장
    auth._save_session([{"name": "prev", "value": "valid"}], {"origins": ["before"]})
    assert session_file.exists()
    before_bytes = session_file.read_bytes()

    # 2) 다음 저장의 직렬화 단계를 강제 실패시킨다 (쓰기 도중 중단 모사)
    def _boom(*args, **kwargs):
        raise RuntimeError("직렬화 중단 모사")

    monkeypatch.setattr(json, "dump", _boom)

    # _save_session 은 예외를 삼키고 로깅만 한다 (계약: 저장 실패가 호출부를 깨지 않음)
    auth._save_session([{"name": "new", "value": "lost"}], {"origins": ["after"]})

    # 3) 직전 유효 세션이 비트 단위로 그대로 보존됐는지
    assert session_file.exists()
    assert session_file.read_bytes() == before_bytes
    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert data["cookies"] == [{"name": "prev", "value": "valid"}]

    # 4) 실패한 tmp 잔여물이 남지 않았는지
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != session_file.name]
    assert leftovers == []


def test_save_session_tmp_file_is_0600_before_replace(tmp_path, monkeypatch):
    """원자 교체에 쓰이는 tmp 파일도 0600 으로 생성된다 (시크릿 노출 창 제거).

    os.replace 를 가로채 교체 직전 tmp 파일의 권한을 검사한다.
    """
    session_file = tmp_path / "session_state.json"
    auth = SSULMSAuthPlaywright(session_file=str(session_file))

    captured = {}
    real_replace = os.replace

    def _spy_replace(src, dst):
        captured["tmp_mode"] = stat.S_IMODE(os.stat(src).st_mode)
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy_replace)

    auth._save_session([], {})

    assert captured.get("tmp_mode") == 0o600
    assert _file_mode(session_file) == 0o600


def test_save_session_uses_same_directory_tmp(tmp_path, monkeypatch):
    """tmp 는 세션 파일과 같은 디렉토리에 만든다 — os.replace 는 동일 파일시스템에서만 원자적."""
    session_file = tmp_path / "session_state.json"
    auth = SSULMSAuthPlaywright(session_file=str(session_file))

    real_replace = os.replace

    def _spy_replace(src, dst):
        assert os.path.dirname(os.path.abspath(src)) == str(tmp_path)
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy_replace)
    auth._save_session([], {})
    assert session_file.exists()


@pytest.mark.parametrize("payload", [([], {}), ([{"name": "c"}], {"origins": []})])
def test_save_session_roundtrip(tmp_path, payload):
    """저장→로드 라운드트립으로 JSON 직렬화가 유지되는지 (다양한 페이로드)."""
    cookies, storage = payload
    session_file = tmp_path / "session_state.json"
    auth = SSULMSAuthPlaywright(session_file=str(session_file))

    auth._save_session(cookies, storage)

    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert data["cookies"] == cookies
    assert data["storage_state"] == storage
