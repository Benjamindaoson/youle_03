'use client';

// 知识库二级页(v4 §31 §281-284)— 用户收藏的 Prompt
import { useState } from 'react';
import { Plus, Sparkles, Trash2 } from 'lucide-react';
import { AppShell } from '@/components/layout/AppShell';
import {
  useCreatePrompt,
  useDeletePrompt,
  usePrompts,
} from '@/lib/api';

export default function PromptsPage() {
  const { data: items = [] } = usePrompts();
  const create = useCreatePrompt();
  const remove = useDeletePrompt();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [content, setContent] = useState('');

  function handleSave() {
    if (!name.trim() || !content.trim()) return;
    create.mutate(
      { name: name.trim(), content: content.trim() },
      {
        onSuccess: () => {
          setAdding(false);
          setName('');
          setContent('');
        },
      },
    );
  }

  return (
    <AppShell>
      <div className="flex h-full flex-col bg-white">
        <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-wechat-line px-5">
          <div>
            <h1 className="text-[15px] font-semibold text-wechat-fg">知识库</h1>
            <p className="text-[11px] text-wechat-mute">
              收藏常用 Prompt,在群里 @提示词名 一键展开
            </p>
          </div>
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="flex items-center gap-1 rounded-sm bg-wechat-green px-3 py-1 text-[12px] text-white hover:bg-[#06AE56]"
          >
            <Plus size={12} /> 新建提示词
          </button>
        </header>

        {adding && (
          <div className="flex flex-col gap-2 border-b border-wechat-line bg-neutral-50 p-4">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="名称(如:反诈标准开场)"
              className="rounded-sm border border-wechat-line bg-white px-2 py-1 text-[13px] outline-none focus:border-wechat-green"
            />
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Prompt 正文……"
              rows={4}
              className="resize-none rounded-sm border border-wechat-line bg-white px-2 py-1 text-[13px] leading-[1.6] outline-none focus:border-wechat-green"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setAdding(false)}
                className="rounded-sm border border-wechat-line bg-white px-3 py-1 text-[12px] text-wechat-fg hover:bg-neutral-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={!name.trim() || !content.trim()}
                className="rounded-sm bg-wechat-green px-3 py-1 text-[12px] text-white disabled:opacity-50"
              >
                保存
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-5">
          {items.length === 0 && !adding ? (
            <div className="grid h-full place-items-center text-[13px] text-wechat-mute">
              <div className="text-center">
                <Sparkles size={28} className="mx-auto text-wechat-mute" />
                <p className="mt-2">还没有收藏 Prompt,点击右上角新建</p>
              </div>
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {items.map((p) => (
                <li
                  key={p.id}
                  className="group rounded-md border border-wechat-line bg-white p-3 hover:border-wechat-green"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-[13px] font-medium text-wechat-fg">
                      {p.name}
                    </span>
                    <div className="flex items-center gap-2">
                      {p.used_count !== undefined && (
                        <span className="text-[10px] text-wechat-mute">
                          已用 {p.used_count} 次
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => remove.mutate(p.id)}
                        className="text-wechat-mute opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <pre className="whitespace-pre-wrap break-words text-[12px] leading-[1.6] text-wechat-sub">
                    {p.content}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </AppShell>
  );
}
