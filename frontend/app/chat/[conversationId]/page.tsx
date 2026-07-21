import { ChatPanel } from '@/components/chat/ChatPanel';

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  return <ChatPanel conversationId={conversationId} />;
}
