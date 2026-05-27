/* Login page */
import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../App';
import { STUDENT_ID_REGEX, resetAllAccounts } from '../auth/AccountStore';
import { clearLmsSession } from '../api/lmsAuth';

export default function LoginPage() {
  const [studentId, setStudentId] = useState('');
  const [password, setPassword]   = useState('');
  const [loading, setLoading]     = useState(false);
  const [errors, setErrors]       = useState({});   // 필드별 inline 에러
  const [formError, setFormError] = useState('');   // 폼 상단 일반 에러
  const [resetting, setResetting] = useState(false);

  // 데모용 — 가입된 모든 계정 + 백엔드 LMS 세션 파일까지 삭제하고 새로고침.
  const handleResetAccounts = async () => {
    if (!confirm('가입된 모든 계정과 LMS 세션을 삭제합니다.\n진행할까요?')) return;
    setResetting(true);
    try {
      resetAllAccounts();
      await clearLmsSession();
    } finally {
      // 새로고침해서 AuthProvider/DataProvider 초기 상태부터 다시 시작
      window.location.replace('/');
    }
  };

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || '/dashboard';

  // ── 폼 검증 ──────────────────────────────────────────────────────
  const validate = () => {
    const e = {};
    if (!studentId.trim()) {
      e.studentId = '학번을 입력해주세요.';
    } else if (!STUDENT_ID_REGEX.test(studentId.trim())) {
      e.studentId = '학번 형식이 올바르지 않습니다. (예: 20231111)';
    }
    if (!password) {
      e.password = '비밀번호를 입력해주세요.';
    }
    return e;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const v = validate();
    setErrors(v);
    setFormError('');
    if (Object.keys(v).length) return;

    setLoading(true);
    const res = await login(studentId.trim(), password);
    setLoading(false);

    if (!res.ok) {
      // AccountStore 가 반환한 에러를 학번 vs 비밀번호 구분해 inline 으로 매핑
      if (res.error.includes('가입된 계정')) {
        setErrors({ studentId: res.error });
      } else if (res.error.includes('비밀번호')) {
        setErrors({ password: res.error });
      } else {
        setFormError(res.error);
      }
      return;
    }
    navigate(from, { replace: true });
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4" style={{ background: 'var(--bg)' }}>
      <div className="w-full max-w-[400px]">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="h-14 w-14 rounded-2xl accent-bg text-white flex items-center justify-center mx-auto mb-4
                          shadow-[0_8px_24px_oklch(48%_0.12_268_/_0.30)]">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 7h7M5 12h14M5 17h10"/>
            </svg>
          </div>
          <div className="text-[22px] font-semibold tracking-tight">LMS Bridge</div>
          <div className="text-[13.5px] text-zinc-500 mt-1">숭실대 스마트캠퍼스 계정으로 로그인</div>
        </div>

        <div className="ssu-card p-7">
          <form onSubmit={handleSubmit} noValidate className="space-y-4">

            {/* 학번 */}
            <div>
              <label className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium block mb-1.5">
                학번
              </label>
              <input
                type="text"
                inputMode="numeric"
                value={studentId}
                onChange={e => { setStudentId(e.target.value); if (errors.studentId) setErrors({ ...errors, studentId: undefined }); }}
                placeholder="20231234"
                autoFocus
                className={`ssu-input mono ${errors.studentId ? 'border-[var(--danger)]' : ''}`}
              />
              {errors.studentId && (
                <div className="text-[11.5px] text-[var(--danger)] mt-1">{errors.studentId}</div>
              )}
            </div>

            {/* 비밀번호 */}
            <div>
              <label className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium block mb-1.5">
                비밀번호
              </label>
              <input
                type="password"
                value={password}
                onChange={e => { setPassword(e.target.value); if (errors.password) setErrors({ ...errors, password: undefined }); }}
                placeholder="가입 시 설정한 비밀번호"
                className={`ssu-input ${errors.password ? 'border-[var(--danger)]' : ''}`}
              />
              {errors.password && (
                <div className="text-[11.5px] text-[var(--danger)] mt-1">{errors.password}</div>
              )}
            </div>

            {/* 폼 일반 에러 */}
            {formError && (
              <div className="text-[12px] text-[var(--danger)] bg-rose-50 border border-rose-200/70 rounded-lg px-3 py-2">
                {formError}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full h-[42px] rounded-lg accent-bg text-white text-[13.5px] font-medium
                         flex items-center justify-center gap-2 hover:opacity-90 disabled:opacity-60 !mt-6"
            >
              {loading
                ? <span className="flex items-center gap-2">
                    <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M21 12a9 9 0 1 1-6.22-8.56"/>
                    </svg>
                    로그인 중…
                  </span>
                : '로그인'}
            </button>
          </form>

          {/* 데모 단계 안내 — 솔직하게 */}
          <div className="mt-5 pt-5 border-t border-[var(--line)] text-[11.5px] text-zinc-500 leading-relaxed flex items-start gap-1.5">
            <span className="shrink-0 mt-0.5">🚧</span>
            <span>
              데모 단계 — 계정 정보가 브라우저 <span className="mono">localStorage</span> 에 저장됩니다.
              비밀번호는 SHA-256 으로 해시되지만, 실제 운영에서는 백엔드 인증으로 교체됩니다.
            </span>
          </div>

          {/* 데모용 — 가입된 모든 계정 / LMS 세션 초기화 */}
          <button
            type="button"
            onClick={handleResetAccounts}
            disabled={resetting}
            className="mt-3 w-full h-9 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-[12px] font-medium hover:bg-rose-100 disabled:opacity-60 flex items-center justify-center gap-1.5"
          >
            {resetting ? '초기화 중…' : '⚠ 모든 계정 / LMS 세션 초기화 (데모용)'}
          </button>
        </div>

        <div className="mt-4 flex items-center justify-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="text-[12.5px] text-zinc-400 hover:text-zinc-700 py-2"
          >
            ← 랜딩 페이지로
          </button>
          <span className="text-zinc-300">|</span>
          <button
            onClick={() => navigate('/signup')}
            className="text-[12.5px] text-[var(--accent)] hover:underline py-2 font-medium"
          >
            계정이 없으신가요? 회원가입 →
          </button>
        </div>
      </div>
    </div>
  );
}
