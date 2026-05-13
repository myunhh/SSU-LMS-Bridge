// src/components/ErrorBoundary.jsx
// React 컴포넌트 트리에서 발생한 에러를 잡아 흰 화면 대신 안내 표시.
// (Hooks 로는 구현 불가 — 반드시 class 컴포넌트)
import { Component } from 'react';

export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // 실서비스에서는 Sentry 등으로 보고
    console.error('[ErrorBoundary]', error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="min-h-screen flex items-center justify-center px-6" style={{ background: 'var(--bg)' }}>
        <div className="ssu-card max-w-[480px] w-full p-8 text-center">
          <div className="text-[42px] mb-3">⚠️</div>
          <div className="text-[18px] font-semibold tracking-tight mb-2">문제가 발생했습니다</div>
          <div className="text-[13px] text-zinc-500 mb-5">
            화면을 그리는 중에 예기치 못한 오류가 발생했어요.
          </div>
          <pre className="text-[11px] mono text-zinc-600 bg-zinc-50 border border-[var(--line)] rounded-md p-3 text-left overflow-x-auto mb-5">
{String(this.state.error?.message || this.state.error)}
          </pre>
          <div className="flex gap-2 justify-center">
            <button
              onClick={() => location.reload()}
              className="h-9 px-4 rounded-lg accent-bg text-white text-[13px] font-medium hover:opacity-90"
            >새로고침</button>
            <button
              onClick={this.reset}
              className="h-9 px-4 rounded-lg border border-[var(--line)] bg-white text-[13px] hover:bg-zinc-50"
            >다시 시도</button>
          </div>
        </div>
      </div>
    );
  }
}
