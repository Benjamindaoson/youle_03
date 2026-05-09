// 与 backend/app/schemas/ws.py 手动同步(WS 事件不走 OpenAPI 自动生成)
import type { components } from './api-types';

export type Conversation = components['schemas']['ConversationOut'] extends never
  ? { id: string; name: string }
  : components['schemas']['ConversationOut'];

export type WSEvent =
  | { type: 'conversation_created'; conversation: Conversation }
  | { type: 'conversation_status_changed'; conversation_id: string; status: string }
  | { type: 'message_added'; message: { id: string; role: string; content: string } }
  | { type: 'step_started'; task_id: string; step_id: string; agent_id: string }
  | {
      type: 'step_completed';
      task_id: string;
      step_id: string;
      artifact: { type: string; reference: string };
    }
  | { type: 'step_streaming'; task_id: string; step_id: string; chunk: string }
  | { type: 'task_completed'; task_id: string; primary_artifact: unknown }
  | { type: 'task_failed'; task_id: string; error: { message: string } }
  | { type: 'clarification_required'; task_id: string; clarification: unknown }
  | { type: 'mode_choice_required'; conversation_id: string; options: unknown[] }
  | {
      type: 'work_mode_changed';
      conversation_id: string;
      from: 'plan' | 'ask' | 'auto';
      to: 'plan' | 'ask' | 'auto';
    }
  | { type: 'brief_updated'; pool_id: string; brief: unknown }
  | {
      type: 'hitl_gate_opened';
      task_id: string;
      gate: {
        id: string;
        step_id: string;
        gate_type: 'version_select' | 'quality_review' | 'final_approval';
      };
      preview_artifact: { type: string; reference: string } | null;
    }
  | {
      type: 'hitl_gate_closed';
      task_id: string;
      resolution: 'approved' | 'modified' | 'rolled_back' | 'timeout';
    }
  | { type: 'quota_warning'; quota_type: string; remaining: number }
  | {
      type: 'agent_status_changed';
      agent_id: string;
      status: 'working' | 'idle' | 'fishing' | 'training';
    }
  | { type: 'pong' };
