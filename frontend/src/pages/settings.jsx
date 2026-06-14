/* Settings view */
import { useState as stS } from 'react';
import { useNavigate } from 'react-router-dom';
import Ist from './icons';
import { useData } from '../data/DataStore';
import { useAuth, useTweaks } from '../App';
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

  // 프로필 편집 (표시 이름 / 학과) — localStorage 저장
  const [profile, setProfile] = stS({ name: USER.name || '', major: USER.major || '' });
  const [savingProfile, setSavingProfile] = stS(false);
  const dirty = profile.name !== (USER.name || '') || profile.major !== (USER.major || '');

  const handleSaveProfile = async () => {
    if (!dirty || !profile.name.trim()) return;
    setSavingProfile(true);
    try {
      const res = await AccountStore.updateProfile(profile);
      if (res.ok) {
        // AuthContext/DataStore 가 localStorage 를 초기값으로 읽으므로 reload 로 반영
        window.location.reload();
      } else {
        window.alert(res.error || '저장에 실패했습니다.');
      }
    } finally {
      setSavingProfile(false);
    }
  };

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
          <button
            onClick={() => setProfile({ name: USER.name || '', major: USER.major || '' })}
            disabled={!dirty || savingProfile}
            className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] disabled:opacity-50 disabled:cursor-not-allowed"
          >취소</button>
          <button
            onClick={handleSaveProfile}
            disabled={!dirty || savingProfile || !profile.name.trim()}
            className="h-8 px-3 rounded-md accent-bg text-white text-[12px] disabled:opacity-50 disabled:cursor-not-allowed"
          >{savingProfile ? '저장 중…' : '변경 저장'}</button>
        </>}>
        <div className="flex items-center gap-4 pb-2">
          <div className="h-16 w-16 rounded-full bg-zinc-200 flex items-center justify-center text-[18px] mono text-zinc-700">{(profile.name || USER.name).slice(0, 2)}</div>
          <div className="flex-1">
            <div className="text-[14px] font-medium">{profile.name || USER.name}</div>
            <div className="text-[11.5px] text-zinc-500 mono">{USER.email}</div>
          </div>
        </div>
        <div className="border-t border-[var(--line-2)] pt-4 space-y-2">
          <Row label="표시 이름">
            <input value={profile.name} onChange={e => setProfile(p => ({ ...p, name: e.target.value }))} className="ssu-input"/>
          </Row>
          <Row label="학과">
            <input value={profile.major} onChange={e => setProfile(p => ({ ...p, major: e.target.value }))} className="ssu-input"/>
          </Row>
          <Row label="기본 학기"><input value={SEMESTER.label} className="ssu-input" readOnly/></Row>
          <Row label="언어">
            <div className="flex gap-1.5">
              <PillBtn active>한국어</PillBtn>
              <PillBtn disabled title="준비 중">English</PillBtn>
              <PillBtn disabled title="준비 중">日本語</PillBtn>
            </div>
          </Row>
          <Row label="시간대"><select className="ssu-input" disabled><option>(GMT+09:00) Asia/Seoul</option></select></Row>
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
          studentId={USER.studentId}
          onRefresh={refreshLms}
          onRelogin={loginLms}
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
  // 이메일 알림은 백엔드 SMTP 가 설정된 항목만 실제 동작한다 (#9).
  // 마감 임박/신규 공지 두 이벤트는 notify_service 가 발송하므로 '이메일' 칩을
  // 활성색으로 표시한다. 단, 발송 on/off·임계 시간은 백엔드 .env(SMTP_*,
  // NOTIFY_*)로 관리하므로 토글 UI 는 의도적으로 두지 않는다(백엔드 단일 소스).
  // 푸시/데스크탑은 service worker 가 필요해 범위 밖 — 계속 '준비 중'.
  return (
    <>
      <SectionCard title="이벤트별 알림"
        sub="이메일 알림은 백엔드 .env 의 SMTP_* · NOTIFY_* 설정으로 동작합니다. 푸시/데스크탑은 준비 중입니다.">
        {[
          { l: '과제 마감 임박',      s: '미제출 과제 (.env NOTIFY_DEADLINE_HOURS)', email: true },
          { l: '새 공지사항',         s: '직전 스캔 이후 게시된 공지', email: true },
          { l: '강의자료 업로드',     s: '주차별 자료가 추가될 때', email: false },
          { l: '동기화 실패',         s: '세션 만료/네트워크 오류', email: false },
          { l: '주간 요약',           s: '월요일 오전 9시', email: false },
        ].map((r,i) => (
          <Row key={i} label={r.l} sub={r.s}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex gap-1.5">
                <Chip outlined>푸시</Chip>
                {r.email ? <Chip>이메일</Chip> : <Chip outlined>이메일</Chip>}
                <Chip outlined>데스크탑</Chip>
              </div>
              {/* 이메일 활성 이벤트는 .env 설정으로 켜진 것을 표시 (백엔드가 단일 소스라 토글은 비활성) */}
              <Switch defaultOn={r.email} disabled/>
            </div>
          </Row>
        ))}
      </SectionCard>

      <SectionCard title="방해 금지" sub="알림 기능은 준비 중입니다.">
        <Row label="조용한 시간" sub="이 시간 동안은 알림을 보내지 않습니다.">
          <div className="flex items-center gap-2">
            <input defaultValue="23:00" className="ssu-input mono w-24" disabled/>
            <span className="text-zinc-400">→</span>
            <input defaultValue="08:00" className="ssu-input mono w-24" disabled/>
          </div>
        </Row>
        <Row label="과목별 음소거">
          <div className="flex flex-wrap gap-1.5">
            {courses.map(c => (
              <button key={c.id} disabled
                className="text-[11.5px] px-2 py-1 rounded-md border border-[var(--line)] opacity-40 cursor-not-allowed flex items-center gap-1.5">
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
              <PillBtn key={t} active={i===3} disabled>{t}</PillBtn>
            ))}
          </div>
        </Row>
        {/* 실행 시각은 백엔드 .env 의 SYNC_HOUR 로 관리한다 — CLAUDE.md 규약상
            'SYNC_HOUR 를 낮추지 말 것'이라 변경 UI 는 의도적으로 구현하지 않는다. */}
        <Row label="실행 시각" sub="백엔드 .env 의 SYNC_HOUR 로 관리됩니다.">
          <input defaultValue="04:00" className="ssu-input mono w-32" disabled/>
        </Row>
        <Row label="병렬 다운로드 워커">
          <div className="flex items-center gap-3">
            <input type="range" min="1" max="8" defaultValue="4" className="flex-1 accent-[var(--accent)]" disabled/>
            <span className="mono text-[12px] w-6 text-right">4</span>
          </div>
        </Row>
        <Row label="실패 시 자동 재시도" sub="지수 백오프 · 최대 3회"><Switch defaultOn disabled/></Row>
      </SectionCard>

      <SectionCard title="동기화 항목" sub="준비 중 — 동기화 대상은 .env 설정으로 결정됩니다.">
        <Row label="공지사항 → Notion DB"><Switch defaultOn disabled/></Row>
        <Row label="과제 → Notion DB"><Switch defaultOn disabled/></Row>
        <Row label="공지/과제 → Obsidian Vault" sub="마크다운 노트로 저장 (강의 파일은 LTI 뷰어 뒤라 범위 밖)"><Switch defaultOn disabled/></Row>
        <Row label="동영상 메타데이터" sub="자막은 v2에서 지원 예정"><Switch disabled/></Row>
        <Row label="제출 내역 → Notion"><Switch disabled/></Row>
      </SectionCard>

      <SectionCard title="대역폭" sub="준비 중 — 아직 적용되지 않습니다.">
        <Row label="다운로드 속도 제한">
          <div className="flex items-center gap-2">
            <input defaultValue="0" className="ssu-input mono w-24" disabled/>
            <span className="text-[11.5px] mono text-zinc-500">MB/s · 0 = 무제한</span>
          </div>
        </Row>
        <Row label="대용량 파일 (>100MB)" sub="Wi-Fi 연결 시에만 다운로드"><Switch defaultOn disabled/></Row>
      </SectionCard>
    </>
  );
}

const ACCENT_COLORS = ['#3a4ca8','#1f2937','#0f766e','#9a3412','#7c3aed'];
const BG_TONES = [{ id: 'warm', l: 'Warm' }, { id: 'cool', l: 'Cool' }, { id: 'mono', l: 'Mono' }];

function AppearanceSection() {
  const { tweaks, updateTweaks } = useTweaks();
  return (
    <>
      <SectionCard title="테마">
        <Row label="모드">
          <div className="grid grid-cols-3 gap-2 max-w-[400px]">
            {[
              { id: 'light', l: '라이트', bg: '#f7f6f3', ready: true },
              { id: 'dark',  l: '다크',   bg: '#0f0f10', ready: false },
              { id: 'auto',  l: '자동',   bg: 'linear-gradient(135deg,#f7f6f3 50%,#0f0f10 50%)', ready: false },
            ].map(t => (
              <button key={t.id} disabled={!t.ready}
                className={`rounded-lg p-3 border text-left
                  ${t.id === 'light' ? 'border-[var(--accent)] ring-accent' : 'border-[var(--line)]'}
                  ${t.ready ? '' : 'opacity-40 cursor-not-allowed'}`}>
                <div className="h-12 rounded-md mb-2 border border-[var(--line-2)]" style={{ background: t.bg }}/>
                <div className="text-[12px] font-medium flex items-center gap-1.5">
                  {t.l}{!t.ready && <span className="text-[10px] text-zinc-400">준비 중</span>}
                </div>
              </button>
            ))}
          </div>
        </Row>
        <Row label="액센트 컬러" sub="앱 전체 강조색 — 즉시 적용되며 이 브라우저에 저장됩니다">
          <div className="flex gap-2">
            {ACCENT_COLORS.map(c => (
              <button key={c} onClick={() => updateTweaks({ accent: c })}
                className={`h-8 w-8 rounded-md border ${tweaks.accent === c ? 'ring-accent border-[var(--accent)]' : 'border-[var(--line)]'}`}
                style={{ background: c }} title={c}/>
            ))}
          </div>
        </Row>
        <Row label="배경 톤">
          <div className="flex gap-1.5">
            {BG_TONES.map(t => (
              <PillBtn key={t.id} active={tweaks.background === t.id}
                onClick={() => updateTweaks({ background: t.id })}>{t.l}</PillBtn>
            ))}
          </div>
        </Row>
      </SectionCard>

      <SectionCard title="레이아웃" sub="준비 중 — 아직 적용되지 않습니다">
        <Row label="밀도">
          <div className="flex gap-1.5">
            <PillBtn disabled>Compact</PillBtn>
            <PillBtn active disabled>Comfortable</PillBtn>
            <PillBtn disabled>Spacious</PillBtn>
          </div>
        </Row>
        <Row label="기본 화면">
          <select className="ssu-input" disabled><option>대시보드</option><option>캘린더</option><option>학습 비서</option></select>
        </Row>
        <Row label="사이드바 위치">
          <div className="flex gap-1.5">
            <PillBtn active disabled>왼쪽</PillBtn>
            <PillBtn disabled>오른쪽</PillBtn>
          </div>
        </Row>
        <Row label="주차 표시" sub="대시보드 헤더 / 캘린더에 주차 번호 노출"><Switch defaultOn disabled/></Row>
      </SectionCard>

      <SectionCard title="글꼴" sub="준비 중 — 아직 적용되지 않습니다">
        <Row label="UI 글꼴"><select className="ssu-input" disabled><option>Pretendard (기본)</option><option>SUIT</option><option>System UI</option></select></Row>
        <Row label="기본 크기">
          <div className="flex items-center gap-3">
            <input type="range" min="12" max="18" defaultValue="14" className="flex-1 accent-[var(--accent)]" disabled/>
            <span className="mono text-[12px] w-10 text-right">14px</span>
          </div>
        </Row>
        <Row label="등폭 글꼴"><select className="ssu-input mono" disabled><option>JetBrains Mono</option><option>D2Coding</option><option>Fira Code</option></select></Row>
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
        { l: '설정 열기',         k: [','] },
      ]}/>
      <Group title="작업" items={[
        { l: '동기화 실행',       k: ['⌘','R'] },
        { l: '메시지 전송 (채팅)',k: ['↵'] },
        { l: '닫기 / 뒤로',       k: ['Esc'] },
      ]}/>
    </>
  );
}

// localStorage 의 ssu_ 접두 키 용량(대략 UTF-16 바이트) 합과 키 수
function _localStorageStats() {
  try {
    let bytes = 0, count = 0, overlayItems = 0;
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith('ssu_')) continue;
      const val = localStorage.getItem(key) || '';
      bytes += (key.length + val.length) * 2;
      count += 1;
      if (key.startsWith('ssu_overrides:')) {
        try {
          const o = JSON.parse(val);
          overlayItems += Object.keys(o.noticesRead || {}).length
            + Object.keys(o.assignmentsSubmitted || {}).length;
        } catch { /* noop */ }
      }
    }
    return { kb: (bytes / 1024).toFixed(1), count, overlayItems };
  } catch {
    return null;
  }
}

function _csvEscape(v) {
  const s = v == null ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function _rowsToCsv(rows) {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(',')];
  for (const r of rows) lines.push(headers.map(h => _csvEscape(r[h])).join(','));
  return lines.join('\n');
}

function DataSection() {
  const { courses, notices, assignments } = useData();
  const stats = _localStorageStats();
  const [fmt, setFmt] = stS('JSON');
  const [scope, setScope] = stS({ courses: true, notices: true, assignments: true });
  const toggleScope = (k) => setScope(s => ({ ...s, [k]: !s[k] }));

  // 캐시 비우기 — 오버레이/세션 메타만 제거. 계정 키(ssu_accounts/ssu_session)는 절대 건드리지 않는다.
  const clearCache = () => {
    const ok = window.confirm(
      '읽음·제출 표시와 세션 메타 캐시를 비웁니다.\n(가입 계정 정보는 삭제되지 않습니다.)'
    );
    if (!ok) return;
    try {
      const toRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith('ssu_overrides:')) toRemove.push(key);
      }
      toRemove.forEach(k => localStorage.removeItem(k));
      localStorage.removeItem('ssu_lms_session_meta');
    } catch { /* noop */ }
    window.location.reload();
  };

  const runExport = () => {
    const data = {};
    if (scope.courses)     data.courses = courses;
    if (scope.notices)     data.notices = notices;
    if (scope.assignments) data.assignments = assignments;
    if (!Object.keys(data).length) { window.alert('내보낼 범위를 선택해주세요.'); return; }

    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    let blob, filename;
    if (fmt === 'CSV') {
      // 범위별 섹션을 헤더와 함께 이어 붙인다.
      const parts = Object.entries(data).map(([k, rows]) => `# ${k}\n${_rowsToCsv(rows)}`);
      blob = new Blob([parts.join('\n\n')], { type: 'text/csv;charset=utf-8' });
      filename = `ssu-lms-export-${stamp}.csv`;
    } else {
      blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      filename = `ssu-lms-export-${stamp}.json`;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <SectionCard title="저장소" sub="이 브라우저(localStorage)에 보관된 데이터입니다.">
        <div className="grid grid-cols-3 gap-3">
          {[
            { l: '로컬 데이터', v: stats ? `${stats.kb} KB` : '—', s: stats ? `ssu_ 키 ${stats.count}개` : '접근 불가' },
            { l: '학사 데이터', v: `${courses.length + notices.length + assignments.length}건`,
              s: `강의 ${courses.length} · 공지 ${notices.length} · 과제 ${assignments.length}` },
            { l: '읽음·제출', v: stats ? `${stats.overlayItems}건` : '—', s: '로컬 오버레이' },
          ].map((s,i) => (
            <div key={i} className="rounded-lg border border-[var(--line)] p-3">
              <div className="text-[10.5px] uppercase tracking-[0.08em] text-zinc-500 font-medium">{s.l}</div>
              <div className="text-[20px] font-semibold tracking-tight mt-1.5">{s.v}</div>
              <div className="text-[11px] text-zinc-500 mt-0.5 mono">{s.s}</div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 pt-1">
          <button onClick={clearCache} className="h-8 px-3 rounded-md border border-[var(--line)] bg-white text-[12px] hover:bg-zinc-50">캐시 비우기</button>
        </div>
      </SectionCard>

      <SectionCard title="내보내기" sub="현재 표시 중인 학사 데이터를 파일로 저장합니다."
        footer={<button onClick={runExport} className="h-8 px-3 rounded-md accent-bg text-white text-[12px]">내보내기 실행</button>}>
        <Row label="형식">
          <div className="flex gap-1.5">
            {['JSON','CSV'].map(f => (
              <PillBtn key={f} active={fmt===f} onClick={() => setFmt(f)}>{f}</PillBtn>
            ))}
          </div>
        </Row>
        <Row label="범위">
          <div className="flex flex-wrap gap-1.5">
            {[['courses','강의'],['notices','공지'],['assignments','과제']].map(([k,l]) => (
              <button key={k} onClick={() => toggleScope(k)}
                className={`text-[11px] px-2 py-0.5 rounded-md border ${scope[k] ? 'bg-[var(--accent-soft)] text-[var(--accent)] border-transparent' : 'border-[var(--line)] text-zinc-700'}`}>
                {l}
              </button>
            ))}
          </div>
        </Row>
      </SectionCard>

      <SectionCard title="개인정보 & 보안">
        <Row label="자격증명 저장 위치"
          sub="데모 단계 — LMS 비밀번호는 브라우저 localStorage 에 저장됩니다. 운영 전환 시 백엔드 .env/vault 로 이전 예정"/>
        <Row label="익명 사용 통계" sub="버그 추적용 · PII 미포함"><Switch disabled/></Row>
        <Row label="LLM 응답 로그 보관" sub="7일 후 자동 삭제"><Switch defaultOn disabled/></Row>
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
      <SectionCard title="업데이트" sub="self-hosted — 자동 업데이터가 없습니다.">
        <Row label="자동 업데이트 확인"><Switch defaultOn disabled/></Row>
        <Row label="릴리스 채널">
          <div className="flex gap-1.5">
            <PillBtn active disabled>Stable</PillBtn>
            <PillBtn disabled>Beta</PillBtn>
            <PillBtn disabled>Nightly</PillBtn>
          </div>
        </Row>
        <div className="text-[11.5px] mono text-[var(--ok)] flex items-center gap-1.5">
          <Ist.Check size={13}/> 최신 버전입니다
        </div>
      </SectionCard>
    </>
  );
}

const PillBtn = ({ children, active, onClick, disabled, title }) => (
  <button
    onClick={disabled ? undefined : onClick}
    disabled={disabled}
    title={title}
    className={`h-7 px-2.5 text-[11.5px] rounded-md border
      ${disabled ? 'opacity-40 cursor-not-allowed border-[var(--line)] text-zinc-500 bg-white'
        : active ? 'bg-zinc-900 text-white border-zinc-900'
        : 'border-[var(--line)] text-zinc-700 hover:bg-zinc-50 bg-white'}`}
  >{children}</button>
);
const Chip = ({ children, outlined }) => (
  <span className={`text-[11px] px-2 py-0.5 rounded-md ${outlined ? 'border border-[var(--line)] text-zinc-700' : 'bg-[var(--accent-soft)] text-[var(--accent)]'}`}>{children}</span>
);
// disabled 면 클릭 무시 + 흐림 표시 (백엔드 없는 비기능 스위치는 일괄 disabled)
function Switch({ defaultOn, disabled }) {
  const [v, setV] = stS(!!defaultOn);
  return (
    <button
      onClick={disabled ? undefined : () => setV(!v)}
      disabled={disabled}
      className={`relative inline-block h-5 w-9 rounded-full transition shrink-0
        ${disabled ? 'opacity-40 cursor-not-allowed bg-zinc-300' : v ? 'accent-bg' : 'bg-zinc-300'}`}
    >
      <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition ${v ? 'left-[18px]' : 'left-0.5'}`}/>
    </button>
  );
}

/* ── LMS 세션 상태 + 액션 (Settings → LMS 연동) ──────────────────────────── */
// onRelogin(studentId, password) → loginLms 와 동일 시그니처.
// ⚠️ 절대 'demo' 같은 가짜 비밀번호로 실제 SSU SSO 를 호출하지 않는다.
//    저장된 자격증명(getLmsCredentials)이 있으면 그것으로 재로그인하고,
//    없으면 비밀번호 입력 UI 를 노출해 사용자가 직접 입력하게 한다.
function LmsSessionRow({ session, busy, studentId, onRefresh, onRelogin, onClear }) {
  const active = session?.active;
  const expiry = active ? formatSessionExpiry(session.savedAt) : '—';
  const age    = active ? formatSessionAge(session.savedAt) : '—';

  // 저장된 LMS 자격증명 유무 — 비활성 상태일 때만 의미 있음.
  // (가입 시 입력한 비밀번호가 localStorage 평문으로 보관됨. 없으면 입력 UI 노출)
  const hasSavedCreds = !active && !!AccountStore.getLmsCredentials();
  // 자격증명이 없을 때 비밀번호 입력 폼 열림 여부
  const [showPwForm, setShowPwForm] = stS(false);
  const [pw, setPw] = stS('');

  // 저장된 자격증명으로 재로그인 (Connectors 페이지의 refreshLms 와 동일 정책)
  const handleSavedRelogin = () => {
    const creds = AccountStore.getLmsCredentials();
    if (!creds?.id || !creds?.password) { setShowPwForm(true); return; }
    onRelogin(creds.id, creds.password);
  };

  // 직접 입력한 비밀번호로 재로그인
  const handleManualRelogin = async () => {
    const password = pw.trim();
    if (!password) return;
    const res = await onRelogin(studentId, password);
    // 성공하면 입력값을 메모리에서 즉시 비운다 (평문 잔존 방지)
    if (res?.ok) { setPw(''); setShowPwForm(false); }
  };

  return (
    <Row label="세션 캐시" sub={
      active
        ? `Playwright storage_state 보관 · 마지막 갱신 ${age}`
        : '세션 없음 — 다시 로그인하면 자동 발급됩니다.'
    }>
      <div className="flex flex-col gap-2">
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
          {!active && hasSavedCreds && (
            <button
              onClick={handleSavedRelogin}
              disabled={busy}
              className="h-7 px-2.5 rounded-md accent-bg text-white text-[11.5px] disabled:opacity-50"
            >
              {busy ? '로그인 중…' : '지금 로그인'}
            </button>
          )}
          {!active && !hasSavedCreds && !showPwForm && (
            <button
              onClick={() => setShowPwForm(true)}
              disabled={busy}
              className="h-7 px-2.5 rounded-md accent-bg text-white text-[11.5px] disabled:opacity-50"
            >
              지금 로그인
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

        {/* 저장된 자격증명이 없을 때만 노출되는 비밀번호 입력 폼.
            'demo' 같은 가짜 비밀번호 대신 사용자가 실제 LMS 비밀번호를 입력한다. */}
        {!active && !hasSavedCreds && showPwForm && (
          <form
            onSubmit={(e) => { e.preventDefault(); handleManualRelogin(); }}
            className="flex flex-col gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--line-2)]/30 p-3"
          >
            <div className="text-[11px] text-zinc-600">
              저장된 LMS 비밀번호가 없습니다. 학번 <span className="mono text-zinc-700">{studentId}</span> 의 비밀번호를 입력하면 세션을 다시 발급합니다.
            </div>
            <div className="flex items-center gap-2">
              <input
                type="password"
                value={pw}
                onChange={(e) => setPw(e.target.value)}
                placeholder="LMS 비밀번호"
                autoComplete="current-password"
                disabled={busy}
                className="ssu-input mono flex-1"
              />
              <button
                type="submit"
                disabled={busy || !pw.trim()}
                className="h-8 px-3 rounded-md accent-bg text-white text-[11.5px] disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
              >
                {busy ? '로그인 중…' : '로그인'}
              </button>
              <button
                type="button"
                onClick={() => { setShowPwForm(false); setPw(''); }}
                disabled={busy}
                className="h-8 px-3 rounded-md border border-[var(--line)] text-[11.5px] hover:bg-zinc-50 disabled:opacity-50 shrink-0"
              >
                취소
              </button>
            </div>
          </form>
        )}
      </div>
    </Row>
  );
}

export { SettingsView };
