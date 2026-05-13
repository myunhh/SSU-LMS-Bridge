// src/pages/not-found.jsx
// 404 페이지 — 존재하지 않는 경로 진입 시
import { useNavigate } from 'react-router-dom';

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex items-center justify-center px-6" style={{ background: 'var(--bg)' }}>
      <div className="ssu-card max-w-[460px] w-full p-10 text-center">
        <div className="text-[72px] font-semibold tracking-tight leading-none mb-2 accent-text mono">404</div>
        <div className="text-[16px] font-semibold mb-1">페이지를 찾을 수 없어요</div>
        <div className="text-[12.5px] text-zinc-500 mb-6">
          주소가 잘못되었거나 페이지가 이동/삭제되었을 수 있어요.
        </div>
        <div className="flex gap-2 justify-center">
          <button
            onClick={() => navigate('/dashboard')}
            className="h-9 px-4 rounded-lg accent-bg text-white text-[13px] font-medium hover:opacity-90"
          >대시보드로</button>
          <button
            onClick={() => navigate(-1)}
            className="h-9 px-4 rounded-lg border border-[var(--line)] bg-white text-[13px] hover:bg-zinc-50"
          >뒤로 가기</button>
        </div>
      </div>
    </div>
  );
}
