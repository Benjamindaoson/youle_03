import { describe, expect, it } from 'vitest';

import { ECOMMERCE_GROUP_ROLES } from './agents';

describe('ECOMMERCE_GROUP_ROLES', () => {
  it('contains only the professional ecommerce group roles', () => {
    expect(ECOMMERCE_GROUP_ROLES).toEqual([
      'ceo_assistant',
      'agent_1',
      'agent_2',
      'agent_3',
    ]);
  });
});
