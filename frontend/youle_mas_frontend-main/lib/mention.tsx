import type { ReactNode } from 'react';

// 高亮文本里的 @xxx
export function highlightMentions(text: string): ReactNode {
  return text.split(/(@\S+)/g).map((part, i) =>
    part.startsWith('@') ? (
      <span key={i} className="font-semibold text-[#5B9DD9]">
        {part}
      </span>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}
