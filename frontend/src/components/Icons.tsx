import type { ReactNode, SVGProps } from "react";

function Icon({ children, ...p }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...p}
    >
      {children}
    </svg>
  );
}

export const SidebarIcon = () => (
  <Icon><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></Icon>
);
export const NewChatIcon = () => (
  <Icon><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></Icon>
);
export const SearchIcon = () => (
  <Icon><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></Icon>
);
export const SendIcon = () => (
  <Icon strokeWidth="2.4"><path d="M12 19V5" /><path d="M5 12l7-7 7 7" /></Icon>
);
export const PlusIcon = () => (
  <Icon><path d="M12 5v14M5 12h14" /></Icon>
);
export const CopyIcon = () => (
  <Icon width="16" height="16"><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></Icon>
);
export const ThumbUpIcon = () => (
  <Icon width="16" height="16"><path d="M7 10v11H3V10zM7 10l4-7a2 2 0 012 2v4h6a2 2 0 012 2.3l-1.5 8A2 2 0 0117.5 21H7" /></Icon>
);
export const ThumbDownIcon = () => (
  <Icon width="16" height="16"><path d="M17 14V3h4v11zM17 14l-4 7a2 2 0 01-2-2v-4H5a2 2 0 01-2-2.3l1.5-8A2 2 0 016.5 3H17" /></Icon>
);
export const RefreshIcon = () => (
  <Icon width="16" height="16"><path d="M21 12a9 9 0 11-3-6.7L21 8" /><path d="M21 3v5h-5" /></Icon>
);
export const ChevronDownIcon = () => (
  <Icon width="16" height="16"><path d="M6 9l6 6 6-6" /></Icon>
);
export const MicIcon = () => (
  <Icon><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></Icon>
);
export const StopIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14"><rect width="14" height="14" rx="3" fill="currentColor" /></svg>
);
export const LogoIcon = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round">
    <path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z" />
    <path d="M12 3v9l7.8 4.5M12 12L4.2 16.5M4.2 7.5L12 12l7.8-4.5" />
  </svg>
);
