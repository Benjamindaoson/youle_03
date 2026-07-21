'use client';

// 主入口 — 未登录或未选模式 → OnboardingFlow
// 已选模式 → 跳到主会话(/chat/main)
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useConversationStore } from '@/stores/conversation';
import { OnboardingFlow } from '@/components/onboarding/OnboardingFlow';

export default function HomePage() {
  const router = useRouter();
  const main = useConversationStore((s) =>
    s.list.find((c) => c.kind === 'main_session'),
  );

  useEffect(() => {
    if (main?.work_mode) router.replace(`/chat/${main.id}`);
  }, [main, router]);

  return <OnboardingFlow />;
}
