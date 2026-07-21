import type { components } from './api-types';

export type Conversation = components['schemas']['ConversationOut'] extends never
  ? { id: string; name: string }
  : components['schemas']['ConversationOut'];

export type EventType = components['schemas']['EventType'];
export type UserEvent = components['schemas']['UserEvent'];
export type WSEvent = UserEvent;
