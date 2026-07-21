'use client';

// 表情系统 — V1 必做(ADR-015):每 Agent 20 组表情
// 严肃场景(金融/医疗/政务)由 Composer 决定不渲染本组件
// 这里以"绿点工程师"为基底,实际后端可按 Agent 拓展独立表情包
const EMOJI_GROUPS: { name: string; items: string[] }[] = [
  { name: '常用', items: ['😀','😁','😂','🤣','😊','😇','🙂','😉','😍','😘','😋','😎','🤩','🥳','🤗','🤔','🤨','😐','😶','😏'] },
  { name: '工作', items: ['💼','📋','📌','✅','📝','📄','📊','📈','📉','📅','🗂','🔖','🔍','💡','🎯','⏰','⌛','📣','🔔','🛠'] },
  { name: '情绪', items: ['😅','😆','😢','😭','😤','😡','🤯','😱','😨','😰','😴','🥱','🤤','😷','🤒','🤕','🤧','🥺','😬','🙄'] },
  { name: '点赞', items: ['👍','👎','👏','🙌','💪','🤝','🤲','🙏','✋','👌','✌️','🤘','👋','🫡','🫶','💯','🎉','✨','🔥','⭐'] },
];

export function EmojiPicker({
  onPick,
  onClose,
}: {
  onPick: (emoji: string) => void;
  onClose: () => void;
}) {
  return (
    <>
      <span className="fixed inset-0 z-30" onClick={onClose} />
      <div className="absolute bottom-[110%] left-3 z-40 w-[320px] overflow-hidden rounded-md border border-wechat-line bg-white shadow-lg">
        <div className="max-h-[300px] overflow-y-auto p-2">
          {EMOJI_GROUPS.map((g) => (
            <div key={g.name} className="mb-2">
              <div className="mb-1 px-1 text-[11px] text-wechat-sub">{g.name}</div>
              <div className="grid grid-cols-10 gap-0.5">
                {g.items.map((e, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onPick(e)}
                    className="h-7 w-7 rounded text-base hover:bg-neutral-100"
                  >
                    {e}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="border-t border-wechat-line bg-neutral-50 px-2 py-1 text-[11px] text-wechat-mute">
          表情 — 严肃场景(金融/医疗/政务)自动关闭
        </div>
      </div>
    </>
  );
}
