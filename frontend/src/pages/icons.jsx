// Inline SVG icon set — small, consistent, 1.5px stroke
const I = ({ children, size = 18, className = '', ...rest }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width={size} height={size}
       fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
       className={className} {...rest}>{children}</svg>
);

const Icon = {
  Home:    (p) => <I {...p}><path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/></I>,
  Book:    (p) => <I {...p}><path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z"/><path d="M4 17a3 3 0 0 1 3-3h11"/></I>,
  Calendar:(p) => <I {...p}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M8 3v4M16 3v4"/></I>,
  Spark:   (p) => <I {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/><circle cx="12" cy="12" r="3"/></I>,
  Plug:    (p) => <I {...p}><path d="M9 7V3M15 7V3M7 7h10v5a5 5 0 0 1-10 0z"/><path d="M12 17v4"/></I>,
  Settings:(p) => <I {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></I>,
  Search:  (p) => <I {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></I>,
  Bell:    (p) => <I {...p}><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21a2 2 0 0 0 4 0"/></I>,
  Send:    (p) => <I {...p}><path d="m4 12 16-8-6 18-3-7-7-3z"/></I>,
  Plus:    (p) => <I {...p}><path d="M12 5v14M5 12h14"/></I>,
  Sync:    (p) => <I {...p}><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/></I>,
  Check:   (p) => <I {...p}><path d="m5 12 5 5 9-11"/></I>,
  Dot:     (p) => <I {...p}><circle cx="12" cy="12" r="4" fill="currentColor"/></I>,
  Chev:    (p) => <I {...p}><path d="m9 6 6 6-6 6"/></I>,
  Down:    (p) => <I {...p}><path d="m6 9 6 6 6-6"/></I>,
  Pin:     (p) => <I {...p}><path d="M12 17v5"/><path d="M9 3h6l-1 6 4 3H6l4-3z"/></I>,
  Clock:   (p) => <I {...p}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></I>,
  File:    (p) => <I {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></I>,
  Code:    (p) => <I {...p}><path d="m9 8-5 4 5 4M15 8l5 4-5 4"/></I>,
  Quiz:    (p) => <I {...p}><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7"/><circle cx="12" cy="17" r=".7" fill="currentColor"/></I>,
  Essay:   (p) => <I {...p}><path d="M4 4h12l4 4v12H4z"/><path d="M8 12h8M8 16h6M8 8h4"/></I>,
  Mail:    (p) => <I {...p}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></I>,
  External:(p) => <I {...p}><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></I>,
  Notion:  (p) => <I {...p}><rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 8v8M9 8l6 8M15 8v8"/></I>,
  Obsidian:(p) => <I {...p}><path d="M12 3 5 8v8l7 5 7-5V8z"/><path d="M12 3v18M5 8l7 5 7-5"/></I>,
  Filter:  (p) => <I {...p}><path d="M3 5h18l-7 9v6l-4-2v-4z"/></I>,
  Sidebar: (p) => <I {...p}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></I>,
  Eye:     (p) => <I {...p}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></I>,
  Sparkles:(p) => <I {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m5 5 2 2M17 17l2 2M5 19l2-2M17 7l2-2"/></I>,
};

export default Icon;
