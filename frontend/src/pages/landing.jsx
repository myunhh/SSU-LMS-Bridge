/* Landing page */
import { useNavigate } from 'react-router-dom';
import Icon from './icons';

export default function LandingPage() {
  const navigate = useNavigate();

  const features = [
    {
      icon: Icon.Book,
      color: 'var(--accent)',
      title: 'LMS 자동 동기화',
      desc: '숭실대 스마트캠퍼스에서 강의자료, 공지, 과제를 자동으로 수집합니다. 세션 캐시로 12배 빠른 재동기화.',
    },
    {
      icon: Icon.Sparkles,
      color: 'oklch(54% 0.14 305)',
      title: 'AI 학습 비서',
      desc: '강의자료를 컨텍스트로 활용하는 RAG 기반 AI 비서. 마감 정리, 개념 설명, 퀴즈 생성을 도와드립니다.',
    },
    {
      icon: Icon.Plug,
      color: 'oklch(58% 0.13 195)',
      title: '다중 커넥터',
      desc: 'Notion, Obsidian, Gmail 등 사용 중인 서비스와 연동해 강의 데이터를 원하는 곳으로 내보냅니다.',
    },
    {
      icon: Icon.Calendar,
      color: 'oklch(58% 0.13 35)',
      title: '통합 캘린더',
      desc: '모든 강의의 마감일, 공지, 시험 일정을 하나의 캘린더에서 관리합니다.',
    },
  ];

  const steps = [
    { n: '01', title: '로그인', desc: '숭실대 학번과 LMS 비밀번호로 1분 안에 계정을 연결합니다.' },
    { n: '02', title: '커넥터 연결', desc: 'Notion, Obsidian, LLM 등 원하는 서비스를 연동합니다.' },
    { n: '03', title: '자동 동기화', desc: '이후 강의자료·공지·과제가 매일 자동으로 업데이트됩니다.' },
  ];

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg)' }}>

      {/* ── Nav ── */}
      <nav className="sticky top-0 z-20 border-b border-[var(--line)] bg-[var(--bg)]/85 backdrop-blur">
        <div className="max-w-[1100px] mx-auto px-6 h-[60px] flex items-center gap-3">
          <div className="flex items-center gap-2.5 flex-1">
            <div className="h-8 w-8 rounded-lg accent-bg text-white flex items-center justify-center shrink-0">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M5 7h7M5 12h14M5 17h10"/>
              </svg>
            </div>
            <span className="text-[14px] font-semibold tracking-tight">LMS Bridge</span>
            <span className="text-[10.5px] mono text-zinc-400 border border-[var(--line)] rounded px-1.5 py-0.5 bg-white hidden sm:inline">ssu</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('/signup')}
              className="h-8 px-4 rounded-lg border border-[var(--line)] bg-white text-[13px] text-zinc-700 font-medium hover:bg-zinc-50"
            >
              회원가입
            </button>
            <button
              onClick={() => navigate('/login')}
              className="h-8 px-4 rounded-lg accent-bg text-white text-[13px] font-medium hover:opacity-90"
            >
              로그인
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="max-w-[1100px] mx-auto px-6 pt-24 pb-20 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--accent-soft)] text-[var(--accent)] text-[12px] mono font-medium mb-7">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] inline-block"/>
          숭실대학교 LMS 자동화 브릿지
        </div>

        <h1 className="text-[52px] font-semibold tracking-tight leading-[1.12] mb-6 text-zinc-900">
          강의, 과제, 공지를<br/>
          <span style={{ color: 'var(--accent)' }}>한 곳에서</span> 관리하세요
        </h1>

        <p className="text-[17px] text-zinc-500 leading-relaxed max-w-[560px] mx-auto mb-10">
          LMS Bridge는 숭실대 스마트캠퍼스 데이터를 자동 수집하고 AI 비서와
          외부 서비스 연동으로 학습 효율을 높여드립니다.
        </p>

        <div className="flex items-center justify-center gap-3 flex-wrap">
          <button
            onClick={() => navigate('/login')}
            className="h-11 px-7 rounded-xl accent-bg text-white text-[14px] font-medium flex items-center gap-2 hover:opacity-90"
          >
            <Icon.Book size={16}/> 지금 시작하기
          </button>
          <button
            onClick={() => navigate('/signup')}
            className="h-11 px-7 rounded-xl border border-[var(--line)] bg-white text-[14px] text-zinc-700 flex items-center gap-2 hover:bg-zinc-50"
          >
            회원가입 →
          </button>
        </div>
      </section>

      {/* ── Stats ── */}
      <div className="max-w-[1100px] mx-auto px-6 mb-20">
        <div className="grid grid-cols-3 gap-4">
          {[
            { n: '7+',   label: '강의 자동 동기화' },
            { n: '4+',   label: '외부 서비스 연동' },
            { n: 'RAG',  label: 'AI 강의자료 분석' },
          ].map((s, i) => (
            <div key={i} className="ssu-card p-6 text-center">
              <div className="text-[32px] font-semibold tracking-tight mono" style={{ color: 'var(--accent)' }}>{s.n}</div>
              <div className="text-[13px] text-zinc-500 mt-1.5">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Features ── */}
      <div className="max-w-[1100px] mx-auto px-6 mb-24">
        <div className="text-center mb-10">
          <div className="text-[10.5px] uppercase tracking-[0.1em] text-zinc-400 font-medium mb-2">기능</div>
          <h2 className="text-[30px] font-semibold tracking-tight">필요한 모든 것, 한 곳에</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {features.map((f, i) => (
            <div key={i} className="ssu-card p-6 flex gap-4 hover:border-zinc-300 transition-colors">
              <div
                className="h-10 w-10 rounded-xl flex items-center justify-center text-white shrink-0"
                style={{ background: f.color }}
              >
                <f.icon size={20}/>
              </div>
              <div>
                <div className="text-[15px] font-semibold mb-1.5">{f.title}</div>
                <div className="text-[13.5px] text-zinc-500 leading-relaxed">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── How it works ── */}
      <div className="border-t border-b border-[var(--line)] bg-white">
        <div className="max-w-[1100px] mx-auto px-6 py-20">
          <div className="text-center mb-12">
            <div className="text-[10.5px] uppercase tracking-[0.1em] text-zinc-400 font-medium mb-2">시작하기</div>
            <h2 className="text-[30px] font-semibold tracking-tight">3단계로 설정 완료</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-10">
            {steps.map((s, i) => (
              <div key={i} className="text-center">
                <div className="text-[40px] font-semibold mono mb-4" style={{ color: 'var(--accent-soft)', WebkitTextStroke: '1px var(--accent)' }}>
                  {s.n}
                </div>
                <div className="text-[15.5px] font-semibold mb-2">{s.title}</div>
                <div className="text-[13.5px] text-zinc-500 leading-relaxed">{s.desc}</div>
              </div>
            ))}
          </div>
          <div className="text-center mt-14">
            <button
              onClick={() => navigate('/login')}
              className="h-11 px-8 rounded-xl accent-bg text-white text-[14px] font-medium hover:opacity-90"
            >
              지금 시작하기 →
            </button>
          </div>
        </div>
      </div>

      {/* ── Footer ── */}
      <footer className="max-w-[1100px] mx-auto w-full px-6 py-6 flex items-center justify-between">
        <div className="text-[12px] text-zinc-400 mono">LMS Bridge · ssu · 2026</div>
        <div className="text-[12px] text-zinc-400">숭실대학교 비공식 학습 도우미</div>
      </footer>
    </div>
  );
}
