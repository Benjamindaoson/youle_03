'use client';

// 原生 WebSocket — 加固清单:
// 1) 指数退避(0.5s → 30s),抖动 ±20%,可见性变化时立即重连
// 2) 心跳:每 25s 发 ping;若 35s 内无 message → 主动 close 触发重连
// 3) 事件去重 + 乱序缓冲:按 event_id(若有)记录最近 200 个 id 的 LRU
// 4) 路由最后一条 lastEventId,持久化到 sessionStorage 以便服务端补偿(可选)
import { useEffect } from 'react';
import { useTaskStore } from '@/stores/task';
import { useWsStore } from '@/stores/ws';
import { useHitlStore } from '@/stores/hitl';
import { useConversationStore } from '@/stores/conversation';
import type { RoleKey, AgentStatus } from '@/lib/agents';

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let pingTimer: ReturnType<typeof setInterval> | null = null;
let watchdogTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;
let manualClose = false;

const seenEventIds = new Set<string>();
const seenOrder: string[] = [];
const SEEN_CAP = 200;

const PING_INTERVAL_MS = 25_000;
const WATCHDOG_MS = 35_000;
const MAX_BACKOFF_MS = 30_000;

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== 'false';

function backoffDelay(attempt: number): number {
  const base = Math.min(500 * 2 ** attempt, MAX_BACKOFF_MS);
  const jitter = (Math.random() - 0.5) * 0.4 * base;
  return Math.max(250, base + jitter);
}

function rememberId(id: string): boolean {
  if (seenEventIds.has(id)) return false;
  seenEventIds.add(id);
  seenOrder.push(id);
  if (seenOrder.length > SEEN_CAP) {
    const drop = seenOrder.shift();
    if (drop) seenEventIds.delete(drop);
  }
  return true;
}

function armWatchdog(token: string | null): void {
  if (watchdogTimer) clearTimeout(watchdogTimer);
  watchdogTimer = setTimeout(() => {
    // 超时无任何消息 → 主动断开,触发 onclose 自动重连
    try {
      socket?.close();
    } catch {
      /* ignore */
    }
  }, WATCHDOG_MS);
}

function startPing(): void {
  if (pingTimer) clearInterval(pingTimer);
  pingTimer = setInterval(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: 'ping', ts: Date.now() }));
      } catch {
        /* ignore */
      }
    }
  }, PING_INTERVAL_MS);
}

function stopTimers(): void {
  if (pingTimer) clearInterval(pingTimer);
  if (watchdogTimer) clearTimeout(watchdogTimer);
  if (reconnectTimer) clearTimeout(reconnectTimer);
  pingTimer = null;
  watchdogTimer = null;
  reconnectTimer = null;
}

export function connectWs(token: string | null): void {
  if (USE_MOCK) return;
  if (socket && socket.readyState <= WebSocket.OPEN) return;
  manualClose = false;

  const lastEventId =
    typeof window !== 'undefined'
      ? sessionStorage.getItem('youle.ws.last_event_id') ?? ''
      : '';
  const url = `${process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws'}${
    token ? `?token=${token}` : ''
  }${lastEventId ? `${token ? '&' : '?'}last_event_id=${encodeURIComponent(lastEventId)}` : ''}`;

  socket = new WebSocket(url);

  socket.onopen = () => {
    reconnectAttempts = 0;
    useWsStore.getState().setConnected(true);
    startPing();
    armWatchdog(token);
  };

  socket.onclose = () => {
    useWsStore.getState().setConnected(false);
    stopTimers();
    if (manualClose) return;
    const delay = backoffDelay(reconnectAttempts++);
    reconnectTimer = setTimeout(() => connectWs(token), delay);
  };

  socket.onerror = () => {
    // 让 onclose 接管重连
    try {
      socket?.close();
    } catch {
      /* ignore */
    }
  };

  socket.onmessage = (ev) => {
    armWatchdog(token);
    try {
      const msg = JSON.parse(ev.data);
      const eid = (msg.event_id || msg.id) as string | undefined;
      if (eid && !rememberId(eid)) return; // 去重
      if (eid && typeof window !== 'undefined') {
        sessionStorage.setItem('youle.ws.last_event_id', eid);
        useWsStore.getState().setLastEventId(eid);
      }
      route(msg);
    } catch {
      /* ignore parse */
    }
  };
}

export function disconnectWs(): void {
  manualClose = true;
  stopTimers();
  socket?.close();
  socket = null;
  reconnectAttempts = 0;
}

function route(msg: { type: string; [k: string]: unknown }): void {
  const task = useTaskStore.getState();
  const hitl = useHitlStore.getState();
  const conv = useConversationStore.getState();
  switch (msg.type) {
    case 'step_started':
      task.upsertStep({
        step_id: msg.step_id as string,
        agent_id: msg.agent_id as string,
        status: 'running',
      });
      break;
    case 'step_streaming':
      task.appendChunk(msg.step_id as string, msg.chunk as string);
      break;
    case 'step_completed':
      task.upsertStep({
        step_id: msg.step_id as string,
        agent_id: '',
        status: 'completed',
        artifact: msg.artifact as never,
      });
      break;
    case 'hitl_gate_opened':
      hitl.push(msg.gate as never);
      break;
    case 'message_added':
      conv.appendMessage(
        msg.message as Parameters<typeof conv.appendMessage>[0],
      );
      break;
    case 'agent_status_changed':
      conv.patchMemberStatus(
        msg.conversation_id as string,
        msg.agent_id as RoleKey,
        msg.status as AgentStatus,
      );
      break;
    case 'work_mode_changed':
      conv.patchMode(
        msg.conversation_id as string,
        msg.to as 'plan' | 'ask' | 'auto',
      );
      break;
    case 'pong':
      break;
    default:
      break;
  }
}

export function useWsLifecycle(token: string | null): void {
  useEffect(() => {
    connectWs(token);

    const onVisible = () => {
      if (document.visibilityState === 'visible' && (!socket || socket.readyState !== WebSocket.OPEN)) {
        // 立即重连一次,不等退避
        reconnectAttempts = 0;
        if (reconnectTimer) clearTimeout(reconnectTimer);
        connectWs(token);
      }
    };
    const onOnline = () => {
      reconnectAttempts = 0;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      connectWs(token);
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisible);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('online', onOnline);
    }

    return () => {
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisible);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('online', onOnline);
      }
      disconnectWs();
    };
  }, [token]);
}
