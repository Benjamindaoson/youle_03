'use client';

// Message stream with the lightweight session intro shown in the design.
import { useEffect, useRef } from 'react';
import { useConversationStore, type Message } from '@/stores/conversation';
import { MessageBubble } from '@/components/chat/MessageBubble';
import type { RoleKey } from '@/lib/agents';

const SESSION_TIME = '15:45';
const JOINED_LABEL = '\u52a0\u5165\u7fa4\u804a';

const NOTICE_NAME: Partial<Record<RoleKey, string>> = {
  ceo_assistant: '\u603b\u7ecf\u7406',
  agent_1: '\u5206\u6790\u5e08',
  agent_2: '\u7b56\u5212\u5e08',
  agent_3: '\u521b\u4f5c\u5e08',
  agent_4: '\u5f71\u97f3\u5e08',
  hr: 'HR',
  finance_manager: '\u8d22\u52a1\u7ecf\u7406',
};

const INTRO_TEXT: Partial<Record<RoleKey, string>> = {
  ceo_assistant:
    '\u8001\u677f\uff0c\u4eba\u5230\u9f50\u4e86\uff01\u4f60\u770b\u6211\u4eec\u505a\u54ea\u4e2a\u8d5b\u9053\u7684\u89c6\u9891\uff1f',
  agent_1:
    '\u6211\u662f\u5206\u6790\u5e08\uff0c\u4e13\u95e8\u505a\u6570\u636e\u548c\u7ade\u54c1\u5206\u6790\u3002\u9700\u8981\u6211\u770b\u54ea\u4e2a\u8d5b\u9053\uff1f',
  agent_2:
    '\u6211\u662f\u7b56\u5212\u5e08\uff0c\u804a\u804a\u4f60\u60f3\u505a\u7684\u65b9\u5411\uff1f\u6211\u53ef\u4ee5\u5e2e\u4f60\u5224\u65ad\u5207\u5165\u8def\u5f84\u3002',
  agent_3:
    '\u6211\u662f\u521b\u4f5c\u5e08\uff0c\u9700\u8981\u6587\u6848\u3001\u65b9\u6848\u7a3f\uff0c\u8fd8\u662f\u8bbe\u8ba1\u6784\u601d\uff1f\u7ed9\u6211\u4e00\u4e2a\u5177\u4f53\u573a\u666f\uff0c\u6211\u76f4\u63a5\u51fa\u7248\u672c\u4f60\u6765\u6311\u3002',
  agent_4:
    '\u6211\u662f\u526a\u8f91\u5e08\uff0c\u8d1f\u8d23\u89c6\u9891\u8282\u594f\u3001\u5206\u955c\u548c\u6210\u7247\u5efa\u8bae\u3002\u65b9\u5411\u5b9a\u4e86\u6211\u5c31\u80fd\u63a5\u4e0a\u3002',
  hr:
    '\u6211\u662f HR\uff0c\u8d1f\u8d23\u56e2\u961f\u6210\u5458\u548c\u6280\u80fd\u914d\u7f6e\u3002\u60f3\u52a0\u4eba\u6216\u5347\u7ea7\u80fd\u529b\u53ef\u4ee5\u627e\u6211\u3002',
  finance_manager:
    '\u6211\u662f\u8d22\u52a1\u7ecf\u7406\uff0c\u8ba2\u9605\u3001\u914d\u989d\u548c\u9884\u7b97\u6211\u6765\u76ef\u7740\uff0c\u9700\u8981\u65f6\u4f1a\u63d0\u9192\u4f60\u3002',
};

export function MessageList({ conversationId }: { conversationId: string }) {
  const messages = useConversationStore(
    (s) => s.messages[conversationId] ?? [],
  );
  const conv = useConversationStore((s) =>
    s.list.find((c) => c.id === conversationId),
  );
  const members = useConversationStore((s) => s.members[conversationId] ?? []);
  const ref = useRef<HTMLDivElement>(null);
  const isGroup = conv?.kind !== 'private_chat';
  const introRoles = members
    .map((member) => member.id)
    .filter((role) => INTRO_TEXT[role]);
  const joinNotice =
    introRoles.length > 0
      ? `${introRoles.map((role) => NOTICE_NAME[role]).filter(Boolean).join('  ')}  ${JOINED_LABEL}`
      : JOINED_LABEL;
  const visibleMessages =
    messages.length > 0 || !isGroup
      ? messages
      : introRoles
          .map((role): Message | null => {
            const text = INTRO_TEXT[role];
            if (!text) return null;
            return {
              id: `intro-${conversationId}-${role}`,
              conversation_id: conversationId,
              kind: 'agent_text',
              role,
              text,
            };
          })
          .filter((message): message is Message => Boolean(message));

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: 'smooth' });
  }, [visibleMessages.length]);

  return (
    <div ref={ref} className="flex flex-col gap-0">
      <div className="mb-5 pt-1 text-center">
        <div className="text-[10px] leading-none text-[#9da3ae]">{SESSION_TIME}</div>
        <div className="mt-6 text-[11px] leading-none text-[#8f96a3]">
          {joinNotice}
        </div>
      </div>

      {visibleMessages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}
