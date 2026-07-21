'use client';

// 设置二级页(v4 §39 §336-341)
import { useState } from 'react';
import { Bell, HelpCircle, LogOut, Monitor, Moon, Shield, Sun } from 'lucide-react';
import clsx from 'clsx';
import { AppShell } from '@/components/layout/AppShell';
import { useUserStore } from '@/stores/user';
import { useRouter } from 'next/navigation';

type Theme = 'light' | 'dark' | 'system';
type Lang = 'zh' | 'en';

export default function SettingsPage() {
  const router = useRouter();
  const logout = useUserStore((s) => s.logout);

  const [notifications, setNotifications] = useState(true);
  const [dataShare, setDataShare] = useState(true);
  const [theme, setTheme] = useState<Theme>('light');
  const [lang, setLang] = useState<Lang>('zh');

  function handleLogout() {
    if (!confirm('确认退出登录?')) return;
    logout();
    router.push('/');
  }

  function handleDeleteData() {
    if (!confirm('删除我的数据(不可恢复),确定?')) return;
    // TODO: call /api/profile/me/erase
    alert('已发起删除申请,72 小时内处理。');
  }

  return (
    <AppShell>
      <div className="flex h-full flex-col overflow-y-auto bg-white">
        <header className="flex h-14 flex-shrink-0 items-center border-b border-wechat-line px-5">
          <h1 className="text-[15px] font-semibold text-wechat-fg">设置</h1>
        </header>

        <div className="mx-auto w-full max-w-2xl space-y-6 p-6">
          <Section title="通知" icon={Bell}>
            <Row label="消息通知" description="新消息桌面提醒">
              <Toggle on={notifications} onChange={setNotifications} />
            </Row>
          </Section>

          <Section title="隐私" icon={Shield}>
            <Row label="数据共享" description="参与产品改进(不含原始内容)">
              <Toggle on={dataShare} onChange={setDataShare} />
            </Row>
            <Row label="删除我的数据" description="清空对话、产物、偏好(不可恢复)">
              <button
                type="button"
                onClick={handleDeleteData}
                className="rounded-sm border border-red-300 px-3 py-1 text-[12px] text-red-600 hover:bg-red-50"
              >
                申请删除
              </button>
            </Row>
          </Section>

          <Section title="界面" icon={Monitor}>
            <Row label="主题">
              <div className="flex gap-1">
                {(['light', 'dark', 'system'] as Theme[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTheme(t)}
                    className={clsx(
                      'flex items-center gap-1 rounded-sm border px-2 py-1 text-[12px]',
                      theme === t
                        ? 'border-wechat-green text-wechat-green'
                        : 'border-wechat-line text-wechat-sub hover:bg-neutral-50',
                    )}
                  >
                    {t === 'light' ? <Sun size={11} /> : t === 'dark' ? <Moon size={11} /> : <Monitor size={11} />}
                    {t === 'light' ? '明亮' : t === 'dark' ? '暗色' : '跟随系统'}
                  </button>
                ))}
              </div>
            </Row>
            <Row label="语言">
              <div className="flex gap-1">
                {(['zh', 'en'] as Lang[]).map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => setLang(l)}
                    className={clsx(
                      'rounded-sm border px-3 py-1 text-[12px]',
                      lang === l
                        ? 'border-wechat-green text-wechat-green'
                        : 'border-wechat-line text-wechat-sub hover:bg-neutral-50',
                    )}
                  >
                    {l === 'zh' ? '中文' : 'English'}
                  </button>
                ))}
              </div>
            </Row>
          </Section>

          <Section title="帮助" icon={HelpCircle}>
            <Row label="使用指南">
              <a
                href="https://github.com/Benjamindaoson/oye-mas"
                target="_blank"
                rel="noreferrer"
                className="text-[12px] text-wechat-green hover:underline"
              >
                查看文档
              </a>
            </Row>
            <Row label="反馈">
              <a
                href="mailto:hello@youle.dev"
                className="text-[12px] text-wechat-green hover:underline"
              >
                hello@youle.dev
              </a>
            </Row>
          </Section>

          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center justify-center gap-2 rounded-sm border border-wechat-line bg-white py-2 text-[13px] text-red-600 hover:bg-red-50"
          >
            <LogOut size={13} /> 退出登录
          </button>
        </div>
      </div>
    </AppShell>
  );
}

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof Bell;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-2 flex items-center gap-1.5 text-[12px] font-medium text-wechat-sub">
        <Icon size={12} /> {title}
      </h2>
      <div className="divide-y divide-wechat-line rounded-md border border-wechat-line bg-white">
        {children}
      </div>
    </section>
  );
}

function Row({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <div className="text-[13px] text-wechat-fg">{label}</div>
        {description && <div className="text-[11px] text-wechat-mute">{description}</div>}
      </div>
      {children}
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!on)}
      className={clsx(
        'relative h-5 w-9 flex-shrink-0 rounded-full transition-colors',
        on ? 'bg-wechat-green' : 'bg-neutral-300',
      )}
    >
      <span
        className={clsx(
          'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all',
          on ? 'left-[18px]' : 'left-0.5',
        )}
      />
    </button>
  );
}
