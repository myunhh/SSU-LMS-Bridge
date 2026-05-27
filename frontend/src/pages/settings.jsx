/* Settings view */
import { useState as stS } from 'react';
import { useNavigate } from 'react-router-dom';
import Ist from './icons';
import { useData } from '../data/DataStore';
import { useAuth } from '../App';
import * as AccountStore from '../auth/AccountStore';
import { SETTINGS_SECTIONS, APP_BRAND } from '../data/uiConfig';
import { formatSessionExpiry, formatSessionAge } from '../api/lmsAuth';

/* ============== Settings ============== */
function SettingsView() {
  const [section, setSection] = stS('account');
  // uiConfig 의 SETTINGS_SECTIONS 는 아이콘을 문자열로 보관 — 여기서 컴포넌트로 resolve
  const sections = SETTINGS_SECTIONS.map(s => ({ ...s, icon: Ist[s.iconName] }));

  return (
    <div className="px-7 py-6 max-w-[1200px]">
      <div className="grid grid-cols-12 gap-5">
        {/* Side nav */}
        <aside className="col-span-12 md:col-span-3">
          <div className="ssu-card p-2 sticky top-4">
            <div className="px-2 pt-2 pb-1.5 text-[10.5px] uppercase tracking-[0.08em] text-zinc-500 font-medium">설정</div>
            <nav className="space-y-0.5">
              {sections.map(s => {
                const I = s.icon;
                const active = section === s.id;
                return (
                  <button key={s.id} onClick={() => setSection(s.id)}
                    className={`w-full flex items-center gap-2.5 px-2.5 h-9 rounded-lg text-[13px] text-left
                      ${active ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'text-zinc-700 hover:bg-zinc-50'}`}>
                    <I size={15}/>
                    <span className="flex-1">{s.label}</span>
                    {active && <Ist.Chev size={13}/>}
                  </button>
                );
              })}
            </nav>
            <div className="m-2 mt-3 p-3 rounded-lg bg-[var(--line-2)]/50 border border-[var(--line)] text-[11px] text-zinc-600 leading-relaxed">
              <div className="mono text-zinc-500 mb-1">{APP_BRAND.version}</div>
              localhost:8000 백엔드와 연결 중. 모든 자격 증명은 <span className="mono">.env</span>에 로컬 보관됩니다.
            </div>
          </div>
        </aside>

        {/* Detail */}
        <section className="col-span-12 md:col-span-9 space-y-5">
          {section === 'account' && <AccountSection/>}
          {section === 'notifications' && <NotificationsSection/>}
          {section === 'sync' && <SyncSection/>}
          {section === 'appearance' && <AppearanceSection/>}
          {section === 'shortcuts' && <ShortcutsSection/>}
          {section === 'data' && <DataSection/>}
          {section === 'about' && <AboutSection/>}
        </section>
      </div>
    </div>
  );
}

function SectionCard({ title, sub, children, footer }) {
  return (
    <div className="ssu-card overflow-hidden">
      <header className="px-5 pt-4 pb-3 border-b border-[var(--line)]">
        <div className="text-[14.5px] font-semibold tracking-tight">{title}</div>
        {sub && <div className="text-[11.5px] text-zinc-500 mt-0.5">{sub}</div>}
      </header>
      <div className="p-5 space-y-4">{children}</div>
      {footer && (
        <footer className="px-5 py-3 border-t border-[var(--line)] flex items-center justify-end gap-2 bg-[var(--line-2)]/30">
          {footer}
        </footer>
      )}
    </div>
  );
}

const Row = ({ label, sub, children }) => (
  <div className="grid grid-cols-12 gap-4 items-center py-1">
    <div className="col-span-12 sm:col-span-4">
      <div className="text-[12.5px] font-medium text-zinc-800">{label}</div>
      {sub && <div className="text-[11px] text-zinc-500 mt-0.5">{sub}</div>}
    </div>
    <div className="col-span-12 sm:col-span-8">{children}</div>
  </div>
);

function AccountSection() {
  const { user: USER, semester: SEMESTER, lmsSession, lmsBusy, loginLms, refreshLms, clearLms } = useData();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [resetting, setResetting] = stS(false);

  // 계정 초기화 — 가입정보(localStorage) + 앱 세션 + LMS 세션(백엔드 파일) 전부 삭제 후 로그아웃
  const handleReset = async () => {
    const ok = window.confirm(
      '정말 계정을 초기화하시겠습니까?\n\n' +
      '· 가입한 계정 정보 (학번/비밀번호 해시/연동 토큰)\n' +
      '· 현재 앱 로그인 세션\n' +
      '· LMS 세션 캐시 (Playwright 쿠키)\n\n' +
      '모두 삭제되며 되돌릴 수 없습니다.'
    );
    if (!ok) return;
    setResetting(true);
    try {
      // 1) 백엔드 LMS 세션 파일 삭제 (실패해도 진행)
      try { await clearLms(); } catch { /* noop */ }
      // 2) localStorage 의 가입 계정 + 세션 + LMS 메타 제거
      AccountStore.resetAllAccounts();
      localStorage.removeItem('ssu_lms_session_meta');
      // 3) AuthContext 로그아웃 + 랜딩으로 이동
      await logout();
      navigate('/', { replace: true });
    } finally {
      setResetting(false);
    }
  };

  return (
    <>
      <SectionCard title="프로필" sub="LMS 계정과 별개로 앱 안에서만 사용합니다."
        footer={<>
          <button className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px]">취소</button>
          <button className="h-8 px-3 rounded-md accent-bg text-white text-[12px]">변경 저장</button>
        </>}>
        <div className="flex items-center gap-4 pb-2">
          <div className="h-16 w-16 rounded-full bg-zinc-200 flex items-center justify-center text-[18px] mono text-zinc-700">{USER.name.slice(0, 2)}</div>
          <div className="flex-1">
            <div className="text-[14px] font-medium">{USER.name}</div>
            <div className="text-[11.5px] text-zinc-500 mono">{USER.email}</div>
          </div>
          <button className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px]">사진 변경</button>
        </div>
        <div className="border-t border-[var(--line-2)] pt-4 space-y-2">
          <Row label="표시 이름"><input defaultValue={USER.name} className="ssu-input"/></Row>
          <Row label="학과"><input defaultValue={USER.major} className="ssu-input"/></Row>
          <Row label="기본 학기"><select className="ssu-input"><option>{SEMESTER.label}</option><option>2025년 2학기</option></select></Row>
          <Row label="언어">
            <div className="flex gap-1.5">
              <PillBtn active>한국어</PillBtn>
              <PillBtn>English</PillBtn>
              <PillBtn>日本語</PillBtn>
            </div>
          </Row>
          <Row label="시간대"><select className="ssu-input"><option>(GMT+09:00) Asia/Seoul</option></select></Row>
        </div>
      </SectionCard>

      <SectionCard title="LMS 연동" sub="canvas.ssu.ac.kr Playwright SSO 자격 증명">
        <Row label="학번"><input key={USER.studentId} defaultValue={USER.studentId} className="ssu-input mono" readOnly/></Row>
        <Row label="비밀번호" sub="가입 시 입력한 LMS 비밀번호로 자동 연결됩니다.">
          <input type="password" defaultValue="••••••••••" className="ssu-input mono" readOnly/>
        </Row>
        <LmsSessionRow
          session={lmsSession}
          busy={lmsBusy}
          onRefresh={refreshLms}
          onRelogin={() => loginLms(USER.studentId, 'demo')}
          onClear={clearLms}
        />
      </SectionCard>

      <SectionCard title="위험 영역">
        <div className="rounded-lg border border-rose-200/60 bg-rose-50/40 p-4">
          <div className="text-[13px] font-medium text-[var(--danger)]">로그아웃 및 로컬 데이터 삭제</div>
          <div className="text-[11.5px] text-zinc-600 mt-1">
            가입 정보(localStorage)·LMS 세션 캐시(.cache)·로컬 메타가 모두 제거되고 랜딩 페이지로 돌아갑니다.
          </div>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="mt-3 h-8 px-3 rounded-md bg-[var(--danger)] text-white text-[12px] hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {resetting ? '삭제 중…' : '계정 초기화'}
          </button>
        </div>
      </SectionCard>
    </>
  );
}

function NotificationsSection() {
  const { courses } = useData();
  return (
    <>
      <SectionCard title="이벤트별 알림" sub="알림은 브라우저 푸시 + (선택) Gmail로 전송됩니다.">
        {[
          { l: '과제 마감 24시간 전', s: '미제출 과제만 알림', def: true },
          { l: '과제 마감 1시간 전',  s: '긴급 알림 (소리)', def: true },
          { l: '새 공지사항',         s: '핀 고정 공지는 즉시', def: true },
          { l: '강의자료 업로드',     s: '주차별 자료가 추가될 때', def: false },
          { l: '동기화 실패',         s: '세션 만료/네트워크 오류', def: true },
          { l: '주간 요약',           s: '월요일 오전 9시', def: false },
        ].map((r,i) => (
          <Row key={i} label={r.l} sub={r.s}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex gap-1.5">
                <Chip>푸시</Chip>
                <Chip outlined>이메일</Chip>
                <Chip outlined>데스크탑</Chip>
              </div>
              <Switch defaultOn={r.def}/>
            </div>
          </Row>
        ))}
      </SectionCard>

      <SectionCard title="방해 금지">
        <Row label="조용한 시간" sub="이 시간 동안은 알림을 보내지 않습니다.">
          <div className="flex items-center gap-2">
            <input defaultValue="23:00" className="ssu-input mono w-24"/>
            <span className="text-zinc-400">→</span>
            <input defaultValue="08:00" className="ssu-input mono w-24"/>
          </div>
        </Row>
        <Row label="과목별 음소거">
          <div className="flex flex-wrap gap-1.5">
            {courses.map(c => (
              <button key={c.id}
                className="text-[11.5px] px-2 py-1 rounded-md border border-[var(--line)] hover:bg-zinc-50 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-sm" style={{background:c.color}}/>
                {c.code}
              </button>
            ))}
          </div>
        </Row>
      </SectionCard>
    </>
  );
}

function SyncSection() {
  return (
    <>
      <SectionCard title="자동 동기화" sub="APScheduler — LMS 새벽 3시 갱신 이후 권장">
        <Row label="동기화 주기">
          <div className="flex gap-1.5">
            {['1시간','3시간','6시간','매일','수동'].map((t,i)=>(
              <PillBtn key={t} active={i===3}>{t}</PillBtn>
            ))}
          </div>
        </Row>
        <Row label="실행 시각" sub="LMS는 매일 새벽 3시에 갱신됩니다.">
          <input defaultValue="04:00" className="ssu-input mono w-32"/>
        </Row>
        <Row label="병렬 다운로드 워커">
          <div className="flex items-center gap-3">
            <input type="range" min="1" max="8" defaultValue="4" className="flex-1 accent-[var(--accent)]"/>
            <span className="mono text-[12px] w-6 text-right">4</span>
          </div>
        </Row>
        <Row label="실패 시 자동 재시도" sub="지수 백오프 · 최대 3회"><Switch defaultOn/></Row>
      </SectionCard>

      <SectionCard title="동기화 항목">
        <Row label="공지사항 → Notion DB"><Switch defaultOn/></Row>
        <Row label="과제 → Notion DB"><Switch defaultOn/></Row>
        <Row label="강의 교안 → Obsidian Vault"><Switch defaultOn/></Row>
        <Row label="동영상 메타데이터" sub="자막은 v2에서 지원 예정"><Switch/></Row>
        <Row label="제출 내역 → Notion"><Switch/></Row>
      </SectionCard>

      <SectionCard title="대역폭" sub="기숙사 등 제한된 환경에서 유용합니다.">
        <Row label="다운로드 속도 제한">
          <div className="flex items-center gap-2">
            <input defaultValue="0" className="ssu-input mono w-24"/>
            <span className="text-[11.5px] mono text-zinc-500">MB/s · 0 = 무제한</span>
          </div>
        </Row>
        <Row label="대용량 파일 (>100MB)" sub="Wi-Fi 연결 시에만 다운로드"><Switch defaultOn/></Row>
      </SectionCard>
    </>
  );
}

function AppearanceSection() {
  const [theme, setTheme] = stS('light');
  return (
    <>
      <SectionCard title="테마">
        <Row label="모드">
          <div className="grid grid-cols-3 gap-2 max-w-[400px]">
            {[
              { id: 'light', l: '라이트', bg: '#f7f6f3', ink: '#18181b' },
              { id: 'dark',  l: '다크',   bg: '#0f0f10', ink: '#fafafa' },
              { id: 'auto',  l: '자동',   bg: 'linear-gradient(135deg,#f7f6f3 50%,#0f0f10 50%)', ink: '#71717a' },
            ].map(t => (
              <button key={t.id} onClick={() => setTheme(t.id)}
                className={`rounded-lg p-3 border text-left ${theme===t.id ? 'border-[var(--accent)] ring-accent' : 'border-[var(--line)]'}`}>
                <div className="h-12 rounded-md mb-2 border border-[var(--line-2)]" style={{ background: t.bg }}/>
                <div className="text-[12px] font-medium">{t.l}</div>
              </button>
            ))}
          </div>
        </Row>
        <Row label="액센트 컬러" sub="앱 전체 강조색 — Tweaks 패널에서도 변경 가능">
          <div className="flex gap-2">
            {['#3a4ca8','#1f2937','#0f766e','#9a3412','#7c3aed'].map(c => (
              <button key={c} className="h-8 w-8 rounded-md border border-[var(--line)]" style={{background:c}}/>
            ))}
          </div>
        </Row>
        <Row label="배경 톤">
          <div className="flex gap-1.5">
            <PillBtn active>Warm</PillBtn>
            <PillBtn>Cool</PillBtn>
            <PillBtn>Mono</PillBtn>
          </div>
        </Row>
      </SectionCard>

      <SectionCard title="레이아웃">
        <Row label="밀도">
          <div className="flex gap-1.5">
            <PillBtn>Compact</PillBtn>
            <PillBtn active>Comfortable</PillBtn>
            <PillBtn>Spacious</PillBtn>
          </div>
        </Row>
        <Row label="기본 화면">
          <select className="ssu-input"><option>대시보드</option><option>캘린더</option><option>학습 비서</option></select>
        </Row>
        <Row label="사이드바 위치">
          <div className="flex gap-1.5">
            <PillBtn active>왼쪽</PillBtn>
            <PillBtn>오른쪽</PillBtn>
          </div>
        </Row>
        <Row label="주차 표시" sub="대시보드 헤더 / 캘린더에 주차 번호 노출"><Switch defaultOn/></Row>
      </SectionCard>

      <SectionCard title="글꼴">
        <Row label="UI 글꼴"><select className="ssu-input"><option>Pretendard (기본)</option><option>SUIT</option><option>System UI</option></select></Row>
        <Row label="기본 크기">
          <div className="flex items-center gap-3">
            <input type="range" min="12" max="18" defaultValue="14" className="flex-1 accent-[var(--accent)]"/>
            <span className="mono text-[12px] w-10 text-right">14px</span>
          </div>
        </Row>
        <Row label="등폭 글꼴"><select className="ssu-input mono"><option>JetBrains Mono</option><option>D2Coding</option><option>Fira Code</option></select></Row>
      </SectionCard>
    </>
  );
}

function ShortcutsSection() {
  const Group = ({ title, items }) => (
    <SectionCard title={title}>
      <div className="divide-y divide-[var(--line-2)]">
        {items.map((it, i) => (
          <div key={i} className="flex items-center justify-between py-2.5 first:pt-0 last:pb-0">
            <div className="text-[12.5px] text-zinc-800">{it.l}</div>
            <div className="flex items-center gap-1">
              {it.k.map((k,j) => (
                <kbd key={j} className="text-[10.5px] mono px-1.5 py-0.5 border border-[var(--line)] rounded bg-white">{k}</kbd>
              ))}
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
  return (
    <>
      <Group title="네비게이션" items={[
        { l: '검색 열기',         k: ['⌘','K'] },
        { l: '대시보드로 이동',   k: ['G','D'] },
        { l: '캘린더로 이동',     k: ['G','C'] },
        { l: '학습 비서 열기',    k: ['G','A'] },
        { l: '커넥터로 이동',     k: ['G','S'] },
        { l: '설정 열기',         k: [',', ''] },
      ]}/>
      <Group title="작업" items={[
        { l: '동기화 실행',       k: ['⌘','R'] },
        { l: '메시지 전송 (채팅)',k: ['⌘','↵'] },
        { l: '새 대화',           k: ['⌘','N'] },
        { l: '체크된 항목 완료',  k: ['X', ''] },
        { l: '닫기 / 뒤로',       k: ['Esc', ''] },
      ]}/>
    </>
  );
}

function DataSection() {
  return (
    <>
      <SectionCard title="저장소">
        <div className="grid grid-cols-3 gap-3">
          {[
            { l: '로컬 DB',     v: '24.6 MB', s: 'SQLite · 7개 강의' },
            { l: 'Vault 파일',  v: '742 MB',  s: '153개 · PDF/PPT' },
            { l: '캐시',        v: '12.1 MB', s: '세션 · 썸네일' },
          ].map((s,i) => (
            <div key={i} className="rounded-lg border border-[var(--line)] p-3">
              <div className="text-[10.5px] uppercase tracking-[0.08em] text-zinc-500 font-medium">{s.l}</div>
              <div className="text-[20px] font-semibold tracking-tight mt-1.5">{s.v}</div>
              <div className="text-[11px] text-zinc-500 mt-0.5 mono">{s.s}</div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 pt-1">
          <button className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] flex items-center gap-1.5">
            <Ist.External size={13}/> Vault 폴더 열기
          </button>
          <button className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px]">캐시 비우기</button>
        </div>
      </SectionCard>

      <SectionCard title="내보내기">
        <Row label="형식">
          <div className="flex gap-1.5">
            <PillBtn active>JSON</PillBtn>
            <PillBtn>CSV</PillBtn>
            <PillBtn>Markdown</PillBtn>
          </div>
        </Row>
        <Row label="범위">
          <div className="flex flex-wrap gap-1.5">
            <Chip>강의</Chip><Chip>공지</Chip><Chip>과제</Chip><Chip outlined>채팅 기록</Chip><Chip outlined>설정</Chip>
          </div>
        </Row>
        <Row label="기간"><select className="ssu-input"><option>전체</option><option>이번 학기</option><option>최근 30일</option></select></Row>
        <div className="pt-2">
          <button className="h-8 px-3 rounded-md accent-bg text-white text-[12px]">내보내기 실행</button>
        </div>
      </SectionCard>

      <SectionCard title="개인정보 & 보안">
        <Row label="자격증명 암호화" sub="OS 키체인에 저장 (macOS Keychain · Windows Credential Manager)"><Switch defaultOn/></Row>
        <Row label="익명 사용 통계" sub="버그 추적용 · PII 미포함"><Switch/></Row>
        <Row label="LLM 응답 로그 보관" sub="7일 후 자동 삭제"><Switch defaultOn/></Row>
      </SectionCard>
    </>
  );
}

function AboutSection() {
  return (
    <>
      <SectionCard title="앱 정보">
        <div className="flex items-start gap-4">
          <div className="h-14 w-14 rounded-xl accent-bg text-white flex items-center justify-center">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 7h7M5 12h14M5 17h10"/>
            </svg>
          </div>
          <div>
            <div className="text-[16px] font-semibold tracking-tight">SSU LMS Bridge</div>
            <div className="text-[11.5px] text-zinc-500 mono mt-0.5">v0.6.2 · build 2026.05.08 · self-hosted</div>
            <div className="text-[12px] text-zinc-700 mt-2 max-w-[520px] leading-relaxed">
              숭실대 스마트캠퍼스 LMS와 LLM/Notion/Obsidian을 연결하는 학습 인프라 통합 도구입니다.
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              <Chip>FastAPI 0.110</Chip>
              <Chip>React 18</Chip>
              <Chip>Playwright</Chip>
              <Chip>litellm</Chip>
              <Chip>APScheduler</Chip>
            </div>
          </div>
        </div>
      </SectionCard>
      <SectionCard title="업데이트">
        <Row label="자동 업데이트 확인"><Switch defaultOn/></Row>
        <Row label="릴리스 채널">
          <div className="flex gap-1.5">
            <PillBtn active>Stable</PillBtn>
            <PillBtn>Beta</PillBtn>
            <PillBtn>Nightly</PillBtn>
          </div>
        </Row>
        <div className="text-[11.5px] mono text-[var(--ok)] flex items-center gap-1.5">
          <Ist.Check size={13}/> 최신 버전입니다
        </div>
      </SectionCard>
    </>
  );
}

const PillBtn = ({ children, active }) => (
  <button className={`h-7 px-2.5 text-[11.5px] rounded-md border ${active ? 'bg-zinc-900 text-white border-zinc-900' : 'border-[var(--line)] text-zinc-700 hover:bg-zinc-50 bg-white'}`}>{children}</button>
);
const Chip = ({ children, outlined }) => (
  <span className={`text-[11px] px-2 py-0.5 rounded-md ${outlined ? 'border border-[var(--line)] text-zinc-700' : 'bg-[var(--accent-soft)] text-[var(--accent)]'}`}>{children}</span>
);
function Switch({ defaultOn }) {
  const [v, setV] = stS(!!defaultOn);
  return (
    <button onClick={() => setV(!v)} className={`relative inline-block h-5 w-9 rounded-full transition shrink-0 ${v ? 'accent-bg' : 'bg-zinc-300'}`}>
      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition ${v ? 'left-[18px]' : 'left-0.5'}`}/>
    </button>
  );
}

/* ── LMS 세션 상태 + 액션 (Settings → LMS 연동) ──────────────────────────── */
function LmsSessionRow({ session, busy, onRefresh, onRelogin, onClear }) {
  const active = session?.active;
  const expiry = active ? formatSessionExpiry(session.savedAt) : '—';
  const age    = active ? formatSessionAge(session.savedAt) : '—';

  return (
    <Row label="세션 캐시" sub={
      active
        ? `Playwright storage_state 보관 · 마지막 갱신 ${age}`
        : '세션 없음 — 다시 로그인하면 자동 발급됩니다.'
    }>
      <div className="flex items-center gap-2 flex-wrap">
        {active ? (
          <span className="text-[11.5px] mono text-[var(--ok)] flex items-center gap-1">
            <Ist.Check size={13}/> 활성 · {expiry}
          </span>
        ) : (
          <span className="text-[11.5px] mono text-zinc-500">비활성</span>
        )}
        <button
          onClick={onRefresh}
          disabled={busy || !active}
          className="h-7 px-2.5 rounded-md border border-[var(--line)] text-[11.5px] hover:bg-zinc-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? '갱신 중…' : '재발급'}
        </button>
        {!active && (
          <button
            onClick={onRelogin}
            disabled={busy}
            className="h-7 px-2.5 rounded-md accent-bg text-white text-[11.5px] disabled:opacity-50"
          >
            {busy ? '로그인 중…' : '지금 로그인'}
          </button>
        )}
        {active && (
          <button
            onClick={onClear}
            disabled={busy}
            className="h-7 px-2.5 rounded-md border border-[var(--line)] text-[11.5px] text-[var(--danger)] hover:bg-rose-50 disabled:opacity-50"
          >
            세션 끊기
          </button>
        )}
      </div>
    </Row>
  );
}

export { SettingsView };
