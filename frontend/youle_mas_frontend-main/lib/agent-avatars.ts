import type { CSSProperties } from 'react';
import type { RoleKey } from '@/lib/agents';

export const ROLE_AVATAR: Partial<Record<RoleKey, CSSProperties>> = {
  ceo_assistant: {
    backgroundImage: 'url(/team-avatar.png)',
    backgroundPosition: '28% 72%',
    backgroundSize: '260%',
  },
  agent_1: {
    backgroundImage: 'url(/avatar.jpg)',
    backgroundPosition: '50% 24%',
    backgroundSize: '180%',
  },
  agent_2: {
    backgroundImage: 'url(/team-avatar.png)',
    backgroundPosition: '72% 27%',
    backgroundSize: '260%',
  },
  agent_3: {
    backgroundImage: 'url(/team-avatar.png)',
    backgroundPosition: '78% 68%',
    backgroundSize: '260%',
  },
  agent_4: {
    backgroundImage: 'url(/team-avatar.png)',
    backgroundPosition: '27% 27%',
    backgroundSize: '260%',
  },
  hr: {
    backgroundImage: 'url(/team-avatar.png)',
    backgroundPosition: '52% 78%',
    backgroundSize: '260%',
  },
  finance_manager: {
    backgroundImage: 'url(/team-avatar.png)',
    backgroundPosition: '48% 38%',
    backgroundSize: '260%',
  },
};
