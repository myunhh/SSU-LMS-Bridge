/* Signup — multi-step onboarding */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../App';
import { useData } from '../data/DataStore';
import { SIGNUP_STEPS as STEPS, SIGNUP_INITIAL as INITIAL } from '../data/uiConfig';
import { STUDENT_ID_REGEX } from '../auth/AccountStore';

// 비밀번호: 8자 이상, 영문/숫자 1개 이상씩 포함
const PASSWORD_RULE = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/;

// 이메일: 흔한 기본 형식 (RFC 전체 대응은 과함. 백엔드에서 더 엄격하게)
const EMAIL_RULE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SignupPage() {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(INITIAL);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const { signup } = useAuth();
  const { loginLms } = useData();
  const navigate = useNavigate();

  const set = (k, v) => {
    setForm(f => ({ ...f, [k]: v }));
    if (errors[k]) setErrors(e => ({ ...e, [k]: undefined }));
  };

  // ── 단계별 검증 ────────────────────────────────────────────────────────────
  const validate = (s) => {
    const e = {};
    if (s === 1) {
      if (!form.name.trim()) {
        e.name = '이름을 입력해주세요.';
      } else if (form.name.trim().length < 2) {
        e.name = '이름은 2자 이상이어야 합니다.';
      }

      if (!form.studentId.trim()) {
        e.studentId = '학번을 입력해주세요.';
      } else if (!STUDENT_ID_REGEX.test(form.studentId.trim())) {
        e.studentId = '학번 형식이 올바르지 않습니다. (예: 20261111)';
      } else {
        // 중복 가입 차단 (로컬 확인)
        try {
          const list = JSON.parse(localStorage.getItem('ssu_accounts') || '[]');
          if (list.some(a => a.studentId === form.studentId.trim())) {
            e.studentId = '이미 가입된 학번입니다.';
          }
        } catch {}
      }

      if (!form.email.trim()) {
        e.email = '이메일을 입력해주세요.';
      } else if (!EMAIL_RULE.test(form.email.trim())) {
        e.email = '이메일 형식이 올바르지 않습니다.';
      } else {
        // 이메일 중복도 차단
        try {
          const list = JSON.parse(localStorage.getItem('ssu_accounts') || '[]');
          const lower = form.email.trim().toLowerCase();
          if (list.some(a => a.email?.toLowerCase() === lower)) {
            e.email = '이미 가입된 이메일입니다.';
          }
        } catch {}
      }

      if (!form.password) {
        e.password = '비밀번호를 입력해주세요.';
      } else if (!PASSWORD_RULE.test(form.password)) {
        e.password = '비밀번호는 8자 이상, 영문과 숫자를 모두 포함해야 합니다.';
      }

      if (form.password !== form.passwordConfirm) {
        e.passwordConfirm = '비밀번호가 일치하지 않습니다.';
      }
    }
    if (s === 2) {
      if (!form.lmsId.trim()) e.lmsId = 'LMS 아이디를 입력해주세요.';
      if (!form.lmsPassword)  e.lmsPassword = 'LMS 비밀번호를 입력해주세요.';
    }
    if (s === 5) {
      if (!form.claudeApiKey.trim()) e.claudeApiKey = 'API 키를 입력해주세요.';
    }
    return e;
  };

  const next = async () => {
    const e = validate(step);
    if (Object.keys(e).length) { setErrors(e); return; }
    setErrors({});

    // Step 2 → 3 전환 시 실제 백엔드 SSO 로그인 수행.
    // 여기서 Playwright 세션이 만들어져야 가입 완료 후 대시보드에서 /api/courses 가 동작한다.
    if (step === 2) {
      setSubmitting(true);
      const res = await loginLms(form.lmsId.trim(), form.lmsPassword);
      setSubmitting(false);
      if (!res.ok) {
        setErrors({ lmsPassword: res.error || 'LMS 로그인에 실패했습니다.' });
        return;
      }
      setStep(s => s + 1);
      return;
    }

    // 마지막 단계가 아니면 다음으로
    if (step < 5) { setStep(s => s + 1); return; }

    // 마지막 단계 — 실제 가입 처리
    setSubmitting(true);
    const res = await signup({
      ...form,
      name:      form.name.trim(),
      studentId: form.studentId.trim(),
      email:     form.email.trim().toLowerCase(),
    });
    setSubmitting(false);

    if (!res.ok) {
      // 가입 실패 — 보통 학번 관련 에러이므로 1단계로 돌려보냄
      setErrors({ submit: res.error });
      setStep(1);
      return;
    }
    navigate('/dashboard', { replace: true });
  };

  const skip = () => { setErrors({}); setStep(s => s + 1); };
  const back = () => { setErrors({}); setStep(s => s - 1); };

  const cur = STEPS[step - 1];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 py-12" style={{ background: 'var(--bg)' }}>
      <div className="w-full max-w-[480px]">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="h-12 w-12 rounded-2xl accent-bg text-white flex items-center justify-center mx-auto mb-4 shadow-[0_8px_24px_oklch(48%_0.12_268_/_0.28)]">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 7h7M5 12h14M5 17h10"/>
            </svg>
          </div>
          <div className="text-[20px] font-semibold tracking-tight">LMS Bridge 시작하기</div>
          <div className="text-[13px] text-zinc-500 mt-1">단계별로 설정을 완료해주세요</div>
        </div>

        {/* Step indicator */}
        <div className="flex items-start mb-7">
          {STEPS.flatMap((s, i) => {
            const done = s.id < step;
            const active = s.id === step;
            const nodes = [
              <div key={`s${s.id}`} className="flex flex-col items-center gap-1.5" style={{ minWidth: 0, flex: '0 0 auto' }}>
                <div className={`h-7 w-7 rounded-full flex items-center justify-center text-[12px] font-semibold transition-all
                  ${done   ? 'accent-bg text-white'
                  : active ? 'accent-bg text-white ring-4 ring-[var(--accent-soft)]'
                           : 'bg-zinc-100 text-zinc-400'}`}>
                  {done ? (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                      <path d="m5 12 5 5 9-11"/>
                    </svg>
                  ) : s.id}
                </div>
                <span className={`text-[9.5px] font-medium text-center leading-tight
                  ${active ? 'text-[var(--accent)]' : done ? 'text-zinc-500' : 'text-zinc-400'}`}>
                  {s.label}
                </span>
              </div>,
            ];
            if (i < STEPS.length - 1) {
              nodes.push(
                <div key={`l${i}`} className={`flex-1 h-px mt-3.5 mx-1 transition-colors
                  ${i < step - 1 ? 'bg-[var(--accent)]' : 'bg-zinc-200'}`}/>
              );
            }
            return nodes;
          })}
        </div>

        {/* Card */}
        <div className="ssu-card p-7">
          {/* Step header */}
          <div className="mb-5 pb-4 border-b border-[var(--line)]">
            <div className="flex items-center gap-2">
              <div className="text-[17px] font-semibold">{cur.label}</div>
              {cur.optional && (
                <span className="text-[10.5px] mono px-1.5 py-0.5 rounded-md bg-zinc-100 text-zinc-500">선택</span>
              )}
            </div>
            <div className="text-[12.5px] text-zinc-500 mt-0.5">{cur.sub}</div>
          </div>

          {/* Fields */}
          <div className="space-y-4">

            {/* ── Step 1: 기본 정보 ── */}
            {step === 1 && <>
              <Field label="이름" error={errors.name}>
                <input className="ssu-input" value={form.name} onChange={e => set('name', e.target.value)} placeholder="홍길동" autoFocus/>
              </Field>
              <Field label="학번" error={errors.studentId}>
                <input className="ssu-input mono" value={form.studentId} onChange={e => set('studentId', e.target.value)} placeholder="20231234"/>
              </Field>
              <Field label="이메일" error={errors.email} hint="알림 수신 및 계정 복구에 사용됩니다.">
                <input
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  className="ssu-input"
                  value={form.email}
                  onChange={e => set('email', e.target.value)}
                  placeholder="your@email.com"
                />
              </Field>
              <Field label="비밀번호" error={errors.password} hint="8자 이상, 영문과 숫자 포함">
                <input type="password" className="ssu-input" value={form.password} onChange={e => set('password', e.target.value)} placeholder="••••••••"/>
              </Field>
              <Field label="비밀번호 확인" error={errors.passwordConfirm}>
                <input type="password" className="ssu-input" value={form.passwordConfirm} onChange={e => set('passwordConfirm', e.target.value)} placeholder="비밀번호 재입력"/>
              </Field>
            </>}

            {/* ── Step 2: LMS ── */}
            {step === 2 && <>
              <InfoBox accent>
                숭실대 스마트캠퍼스(canvas.ssu.ac.kr) 로그인 정보입니다.
                비밀번호는 암호화되어 저장되며 LMS 인증에만 사용됩니다.
                "다음" 클릭 시 백엔드가 SSO 로그인을 수행하므로 5~10초 정도 걸려요.
              </InfoBox>
              <Field label="LMS 아이디 (학번)" error={errors.lmsId}>
                <input className="ssu-input mono" value={form.lmsId} onChange={e => set('lmsId', e.target.value)} placeholder="20231234" autoFocus/>
              </Field>
              <Field label="LMS 비밀번호" error={errors.lmsPassword}>
                <input type="password" className="ssu-input" value={form.lmsPassword} onChange={e => set('lmsPassword', e.target.value)} placeholder="스마트캠퍼스 비밀번호"/>
              </Field>
            </>}

            {/* ── Step 3: Notion ── */}
            {step === 3 && <>
              <InfoBox>
                Notion → 설정 → 연동 → 내부 통합에서 토큰을 발급받아 입력해주세요.
                연동을 건너뛰어도 나중에 커넥터 설정에서 추가할 수 있습니다.
              </InfoBox>
              <Field label="Internal Integration Token" error={errors.notionToken}>
                <input className="ssu-input mono" value={form.notionToken} onChange={e => set('notionToken', e.target.value)} placeholder="secret_…" autoFocus/>
              </Field>
              <Field label="루트 페이지 ID" error={errors.notionPageId} hint="강의 자료를 내보낼 Notion 페이지의 ID">
                <input className="ssu-input mono" value={form.notionPageId} onChange={e => set('notionPageId', e.target.value)} placeholder="33b65931485c800b…"/>
              </Field>
            </>}

            {/* ── Step 4: Obsidian ── */}
            {step === 4 && <>
              <InfoBox>
                Obsidian → Local REST API 플러그인을 설치한 후 Auth Code를 발급해주세요.
                연동을 건너뛰어도 나중에 커넥터 설정에서 추가할 수 있습니다.
              </InfoBox>
              <Field label="Auth Code" error={errors.obsidianAuthCode}>
                <input className="ssu-input mono" value={form.obsidianAuthCode} onChange={e => set('obsidianAuthCode', e.target.value)} placeholder="obs_…" autoFocus/>
              </Field>
              <Field label="Vault 이름" error={errors.obsidianVault}>
                <input className="ssu-input mono" value={form.obsidianVault} onChange={e => set('obsidianVault', e.target.value)}/>
              </Field>
              <Field label="MCP Endpoint" error={errors.obsidianEndpoint}>
                <input className="ssu-input mono" value={form.obsidianEndpoint} onChange={e => set('obsidianEndpoint', e.target.value)}/>
              </Field>
            </>}

            {/* ── Step 5: Claude API ── */}
            {step === 5 && <>
              <InfoBox>
                console.anthropic.com → API Keys에서 키를 발급받아 입력해주세요.
                키는 암호화되어 저장되며 학습 비서 기능에만 사용됩니다.
              </InfoBox>
              <Field label="Anthropic API Key" error={errors.claudeApiKey}>
                <input type="password" className="ssu-input mono" value={form.claudeApiKey} onChange={e => set('claudeApiKey', e.target.value)} placeholder="sk-ant-…" autoFocus/>
              </Field>
              <Field label="기본 모델">
                <select className="ssu-input" value={form.claudeModel} onChange={e => set('claudeModel', e.target.value)}
                  style={{ appearance: 'none', backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.45)' d='M0 0h10L5 6z'/></svg>")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center' }}>
                  <option value="claude-haiku-4-5">claude-haiku-4-5 — 빠름 · 저비용</option>
                  <option value="claude-sonnet-4-6">claude-sonnet-4-6 — 균형</option>
                  <option value="claude-opus-4-7">claude-opus-4-7 — 최고 성능</option>
                </select>
              </Field>
            </>}
          </div>

          {/* 가입 단계 전체에서 발생한 일반 에러 */}
          {errors.submit && (
            <div className="mt-4 text-[12px] text-[var(--danger)] bg-rose-50 border border-rose-200/70 rounded-lg px-3 py-2">
              {errors.submit}
            </div>
          )}

          {/* Buttons */}
          <div className="flex items-center gap-2.5 mt-6 pt-5 border-t border-[var(--line)]">
            {step > 1 ? (
              <button onClick={back} disabled={submitting}
                className="h-[42px] px-5 rounded-lg border border-[var(--line)] bg-white text-[13px] text-zinc-700 hover:bg-zinc-50 shrink-0 disabled:opacity-60">
                ← 이전
              </button>
            ) : (
              <button onClick={() => navigate('/login')} disabled={submitting}
                className="h-[42px] px-5 rounded-lg border border-[var(--line)] bg-white text-[13px] text-zinc-700 hover:bg-zinc-50 shrink-0 disabled:opacity-60">
                로그인
              </button>
            )}
            <button onClick={next} disabled={submitting}
              className="flex-1 h-[42px] rounded-lg accent-bg text-white text-[13.5px] font-medium hover:opacity-90 disabled:opacity-60 flex items-center justify-center gap-2">
              {submitting && (
                <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M21 12a9 9 0 1 1-6.22-8.56"/>
                </svg>
              )}
              {step === 5
                ? (submitting ? '가입 중…' : '설정 완료 →')
                : step === 2 && submitting
                  ? 'LMS 로그인 중…'
                  : '다음 →'}
            </button>
          </div>
        </div>

        {/* Skip for optional steps */}
        {cur.optional && (
          <button onClick={skip}
            className="mt-3 w-full text-center text-[12px] text-zinc-400 hover:text-zinc-600 py-2 transition-colors">
            건너뛰고 나중에 설정하기 →
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Local helpers ── */
function Field({ label, error, hint, children }) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium block mb-1.5">
        {label}
      </label>
      {children}
      {hint && !error && <div className="text-[11px] text-zinc-400 mt-1">{hint}</div>}
      {error && <div className="text-[11.5px] text-[var(--danger)] mt-1">{error}</div>}
    </div>
  );
}

function InfoBox({ children, accent }) {
  return (
    <div className={`rounded-lg px-4 py-3 text-[12px] leading-relaxed border
      ${accent
        ? 'bg-[var(--accent-soft)] border-[var(--accent)]/20 text-[var(--accent)]'
        : 'bg-zinc-50 border-[var(--line)] text-zinc-600'}`}>
      {children}
    </div>
  );
}
