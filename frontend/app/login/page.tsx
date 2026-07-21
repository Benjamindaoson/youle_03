'use client';

// 登录页(v4 §38 #332-335)— 短信验证码登录
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useUserStore } from '@/stores/user';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== 'false';

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useUserStore((s) => s.setAuth);

  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'phone' | 'code'>('phone');
  const [counter, setCounter] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function startCounter() {
    setCounter(60);
    const t = setInterval(() => {
      setCounter((c) => {
        if (c <= 1) {
          clearInterval(t);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }

  async function sendCode() {
    setErr(null);
    if (!/^\d{11}$/.test(phone)) {
      setErr('请输入 11 位手机号');
      return;
    }
    setLoading(true);
    try {
      if (!USE_MOCK) {
        const r = await fetch(`${BASE}/api/auth/sms/send`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ phone }),
        });
        if (!r.ok) throw new Error(`${r.status}`);
      }
      setStep('code');
      startCounter();
    } catch (e) {
      setErr(`发送失败: ${e instanceof Error ? e.message : 'unknown'}`);
    } finally {
      setLoading(false);
    }
  }

  async function login() {
    setErr(null);
    if (!/^\d{6}$/.test(code)) {
      setErr('请输入 6 位验证码');
      return;
    }
    setLoading(true);
    try {
      if (USE_MOCK) {
        setAuth({ id: 'mock-user', phone, nickname: `用户${phone.slice(-4)}` }, 'mock-token');
      } else {
        const r = await fetch(`${BASE}/api/auth/login`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ phone, code }),
        });
        if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
        const data = await r.json();
        setAuth(
          { id: data.user_id, phone, nickname: `用户${phone.slice(-4)}` },
          data.access_token,
        );
      }
      router.push('/');
    } catch (e) {
      setErr(`登录失败: ${e instanceof Error ? e.message : 'unknown'}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-wechat-bg">
      <div className="w-[360px] rounded-md border border-wechat-line bg-white p-6 shadow-sm">
        <h1 className="mb-1 text-center text-[17px] font-semibold text-wechat-fg">
          登录「有了」
        </h1>
        <p className="mb-4 text-center text-[12px] text-wechat-mute">
          你的专属 AI 工作团队
        </p>

        {step === 'phone' ? (
          <>
            <label className="mb-1 block text-[12px] text-wechat-sub">手机号</label>
            <input
              autoFocus
              value={phone}
              onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
              placeholder="13800138000"
              maxLength={11}
              className="mb-3 w-full rounded-sm border border-wechat-line bg-white px-2 py-1.5 text-[13px] outline-none focus:border-wechat-green"
            />
            <button
              type="button"
              onClick={sendCode}
              disabled={loading}
              className="w-full rounded-sm bg-wechat-green py-2 text-[13px] text-white hover:bg-[#06AE56] disabled:opacity-50"
            >
              {loading ? '发送中…' : '获取验证码'}
            </button>
          </>
        ) : (
          <>
            <label className="mb-1 block text-[12px] text-wechat-sub">
              验证码已发送至 {phone}
            </label>
            <input
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              placeholder="6 位验证码"
              maxLength={6}
              className="mb-3 w-full rounded-sm border border-wechat-line bg-white px-2 py-1.5 text-[13px] outline-none focus:border-wechat-green"
            />
            <div className="mb-3 flex items-center justify-between text-[11px]">
              <button
                type="button"
                onClick={() => setStep('phone')}
                className="text-wechat-sub hover:text-wechat-fg"
              >
                ← 改手机号
              </button>
              <button
                type="button"
                disabled={counter > 0 || loading}
                onClick={sendCode}
                className="text-wechat-green disabled:text-wechat-mute"
              >
                {counter > 0 ? `${counter}s 后重发` : '重新发送'}
              </button>
            </div>
            <button
              type="button"
              onClick={login}
              disabled={loading}
              className="w-full rounded-sm bg-wechat-green py-2 text-[13px] text-white hover:bg-[#06AE56] disabled:opacity-50"
            >
              {loading ? '登录中…' : '登录'}
            </button>
          </>
        )}

        {err && (
          <div className="mt-3 rounded-sm bg-red-50 px-2 py-1.5 text-center text-[11px] text-red-600">
            {err}
          </div>
        )}

        <p className="mt-5 text-center text-[10px] text-wechat-mute">
          登录即同意《用户协议》《隐私政策》
        </p>
      </div>
    </main>
  );
}
