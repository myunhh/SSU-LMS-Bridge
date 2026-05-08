/* Login page */
import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../App';

export default function LoginPage() {
  const [studentId, setStudentId] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || '/dashboard';

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!studentId.trim() || !password.trim()) {
      setError('학번과 비밀번호를 입력해주세요.');
      return;
    }
    setLoading(true);
    setError('');
    await new Promise(r => setTimeout(r, 700));
    login(studentId.trim(), password);
    navigate(from, { replace: true });
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4" style={{ background: 'var(--bg)' }}>

      {/* Card */}
      <div className="w-full max-w-[400px]">

        {/* Logo */}
        <div className="text-center mb-8">
          <div
            className="h-14 w-14 rounded-2xl accent-bg text-white flex items-center justify-center mx-auto mb-4
                       shadow-[0_8px_24px_oklch(48%_0.12_268_/_0.30)]"
          >
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 7h7M5 12h14M5 17h10"/>
            </svg>
          </div>
          <div className="text-[22px] font-semibold tracking-tight">LMS Bridge</div>
          <div className="text-[13.5px] text-zinc-500 mt-1">숭실대 스마트캠퍼스 계정으로 로그인</div>
        </div>

        <div className="ssu-card p-7">
          <form onSubmit={handleSubmit} className="space-y-4">

            <div>
              <label className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium block mb-1.5">
                학번
              </label>
              <input
                type="text"
                value={studentId}
                onChange={e => setStudentId(e.target.value)}
                placeholder="20231234"
                autoFocus
                className="ssu-input"
              />
            </div>

            <div>
              <label className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium block mb-1.5">
                비밀번호
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="LMS 비밀번호 입력"
                className="ssu-input"
              />
            </div>

            {error && (
              <div className="text-[12px] text-[var(--danger)] bg-rose-50 border border-rose-200/70 rounded-lg px-3 py-2">
                {error}
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

          <div className="mt-5 pt-5 border-t border-[var(--line)] text-[11.5px] text-zinc-400 leading-relaxed flex items-start gap-1.5">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="shrink-0 mt-0.5">
              <rect x="3" y="11" width="18" height="11" rx="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            비밀번호는 LMS 인증에만 사용되며 서버에 평문으로 저장되지 않습니다.
          </div>
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
