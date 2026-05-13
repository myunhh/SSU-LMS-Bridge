// src/components/Toast.jsx
// ──────────────────────────────────────────────────────────────────────────────
// 글로벌 알림(toast) 시스템.
//
// 사용 예:
//   const toast = useToast();
//   toast({ kind: 'success', text: '저장됨' });
//   toast({ kind: 'error', text: '실패', duration: 5000 });
//
// 종류(kind): success | error | info | warning
// ──────────────────────────────────────────────────────────────────────────────
import { createContext, useContext, useState, useCallback, useEffect } from 'react';

const ToastContext = createContext(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast() 는 <ToastProvider> 안에서만 사용 가능합니다.');
  return ctx;
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts(ts => ts.filter(t => t.id !== id));
  }, []);

  const toast = useCallback((opts) => {
    const id = Date.now() + Math.random();
    const duration = opts.duration ?? 3000;
    setToasts(ts => [...ts, { id, kind: opts.kind || 'info', text: opts.text }]);
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration);
    }
    return id;
  }, [dismiss]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <Toaster toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

// ── 화면 표시 컴포넌트 ────────────────────────────────────────────────────────
function Toaster({ toasts, onDismiss }) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map(t => <ToastItem key={t.id} {...t} onDismiss={() => onDismiss(t.id)} />)}
    </div>
  );
}

function ToastItem({ kind, text, onDismiss }) {
  const [show, setShow] = useState(false);
  useEffect(() => { setShow(true); }, []);

  const palette = {
    success: { dot: 'var(--ok)',     bg: 'white' },
    error:   { dot: 'var(--danger)', bg: 'white' },
    warning: { dot: 'var(--warn)',   bg: 'white' },
    info:    { dot: 'var(--accent)', bg: 'white' },
  }[kind] || { dot: 'var(--accent)', bg: 'white' };

  return (
    <div
      className={`pointer-events-auto ssu-card px-4 py-3 min-w-[260px] max-w-[420px] flex items-center gap-3 shadow-md transition-all duration-200
        ${show ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0'}`}
      style={{ background: palette.bg }}
    >
      <span className="h-2 w-2 rounded-full shrink-0" style={{ background: palette.dot }} />
      <div className="flex-1 text-[13px] text-zinc-800 leading-snug">{text}</div>
      <button
        onClick={onDismiss}
        className="text-zinc-400 hover:text-zinc-700 text-[14px] leading-none"
        aria-label="닫기"
      >×</button>
    </div>
  );
}
