'use client';

// Agent 履历卡片(v4 §232-241)
// - 悬停 0.3s / 点击头像出现
// - 操作:[私聊] [查看更多] [分享名片]
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ExternalLink,
  MessageCircle,
  Share2,
  Sparkles,
} from 'lucide-react';
import { ROLES, type RoleKey } from '@/lib/agents';

const MODEL_BY_ROLE: Record<RoleKey, string> = {
  user: '—',
  ceo_assistant: 'deepseek-v4-flash',
  agent_1: 'kimi-k2 / claude-sonnet-4-6 / deepseek-v4-pro',
  agent_2: 'python-pptx / openpyxl / pillow',
  agent_3: 'gpt-image-2 / seedream-3 / claude-sonnet-vision',
  agent_4: 'volcengine-tts / whisper-v3 / ffmpeg',
  hr: 'deepseek-v4-flash',
  finance_manager: 'deepseek-v4-flash',
};

const SPECIALTIES_BY_ROLE: Record<RoleKey, string[]> = {
  user: [],
  ceo_assistant: ['意图理解', '任务编排', '澄清', '中断处理'],
  agent_1: ['短文', '长文', '研究', '分析', '翻译'],
  agent_2: ['Excel', 'Word', '长图拼接', 'PDF 提取'],
  agent_3: ['文生图', '风格分析', '质量校验', 'OCR'],
  agent_4: ['TTS', 'Whisper', 'BGM', '视频合成'],
  hr: ['Agent 推荐', 'Skill 引导', '能力边界'],
  finance_manager: ['配额查询', '账单', '续费', '提醒'],
};

const PLATFORM_TOTAL_BY_ROLE: Record<RoleKey, number> = {
  user: 0,
  ceo_assistant: 1_240_000,
  agent_1: 980_000,
  agent_2: 124_000,
  agent_3: 632_000,
  agent_4: 215_000,
  hr: 410_000,
  finance_manager: 380_000,
};

export interface AgentCardData {
  role: RoleKey;
  personalCount?: number;
}

interface Props {
  data: AgentCardData;
  /** 锚点位置:相对于父元素 */
  anchorRect: DOMRect | null;
  onClose: () => void;
  onPrivateChat?: () => void;
}

export function AgentProfileCard({
  data,
  anchorRect,
  onClose,
  onPrivateChat,
}: Props) {
  const router = useRouter();
  const meta = ROLES[data.role];
  const [position, setPosition] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!anchorRect) return;
    const cardWidth = 280;
    const cardHeight = 240;
    let top = anchorRect.bottom + 6;
    let left = anchorRect.left;
    if (top + cardHeight > window.innerHeight) top = anchorRect.top - cardHeight - 6;
    if (left + cardWidth > window.innerWidth) left = window.innerWidth - cardWidth - 8;
    setPosition({ top: Math.max(8, top), left: Math.max(8, left) });
  }, [anchorRect]);

  function shareCard() {
    const text = `${meta.name} · ${meta.description ?? ''} · 来自「有了」AI 工作团队`;
    if (navigator.share) {
      void navigator.share({ title: meta.name, text });
    } else {
      void navigator.clipboard?.writeText(text);
      alert('名片文本已复制');
    }
  }

  return (
    <>
      <span
        className="fixed inset-0 z-40"
        onClick={onClose}
        onMouseDown={onClose}
      />
      <div
        className="fixed z-50 w-[280px] rounded-md border border-wechat-line bg-white shadow-xl"
        style={{ top: position.top, left: position.left }}
      >
        {/* 头部 */}
        <div className="flex items-start gap-3 border-b border-wechat-line p-3">
          <span
            className="grid h-12 w-12 flex-shrink-0 place-items-center rounded text-[16px] font-bold text-white"
            style={{ background: meta.color }}
          >
            {meta.initial}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold text-wechat-fg">{meta.name}</div>
            <div className="text-[11px] text-wechat-sub">{meta.description}</div>
            <div className="mt-1 flex items-center gap-1 text-[10px] text-wechat-mute">
              <Sparkles size={10} /> {MODEL_BY_ROLE[data.role]}
            </div>
          </div>
        </div>

        {/* 专业标识 */}
        <div className="border-b border-wechat-line p-3">
          <div className="mb-1 text-[10px] font-medium text-wechat-mute">擅长</div>
          <div className="flex flex-wrap gap-1">
            {SPECIALTIES_BY_ROLE[data.role].map((s) => (
              <span
                key={s}
                className="rounded-sm bg-wechat-green-soft px-1.5 py-0.5 text-[10px] text-wechat-green"
              >
                {s}
              </span>
            ))}
          </div>
        </div>

        {/* 服务统计 */}
        <div className="border-b border-wechat-line p-3 text-[11px]">
          <div className="flex justify-between text-wechat-sub">
            <span>已为你完成</span>
            <span className="tabular-nums text-wechat-fg">
              {data.personalCount ?? 0} 次
            </span>
          </div>
          <div className="mt-1 flex justify-between text-wechat-sub">
            <span>平台累计</span>
            <span className="tabular-nums text-wechat-fg">
              {PLATFORM_TOTAL_BY_ROLE[data.role].toLocaleString('zh-CN')} 次
            </span>
          </div>
        </div>

        {/* 操作 */}
        <div className="flex divide-x divide-wechat-line">
          <button
            type="button"
            onClick={() => {
              onClose();
              if (onPrivateChat) onPrivateChat();
              else router.push(`/chat/private/${data.role}`);
            }}
            className="flex flex-1 items-center justify-center gap-1 py-2 text-[12px] text-wechat-fg hover:bg-neutral-50"
          >
            <MessageCircle size={12} /> 私聊
          </button>
          <button
            type="button"
            onClick={shareCard}
            className="flex flex-1 items-center justify-center gap-1 py-2 text-[12px] text-wechat-fg hover:bg-neutral-50"
          >
            <Share2 size={12} /> 名片
          </button>
          <button
            type="button"
            onClick={() => {
              onClose();
              router.push(`/agent/${data.role}`);
            }}
            className="flex flex-1 items-center justify-center gap-1 py-2 text-[12px] text-wechat-fg hover:bg-neutral-50"
          >
            <ExternalLink size={12} /> 详情
          </button>
        </div>
      </div>
    </>
  );
}
