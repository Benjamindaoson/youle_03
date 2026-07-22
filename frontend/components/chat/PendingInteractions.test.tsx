import { describe, expect, it } from 'vitest';

import {
  approvalPayload,
  imageConfirmationDetails,
} from './PendingInteractions';
import type { HITLGate } from '@/stores/hitl';

const imageGate = {
  id: 'gate-1',
  task_id: 'task-1',
  step_id: 'segment_images',
  gate_type: 'image_generation_confirmation',
  resolution: null,
  preview_artifact: {
    metadata: {
      image_count: 5,
      provider: '火山方舟',
      model: 'doubao-seedream-4-0-250828',
      estimated_cost_cny_per_image: 0.2,
    },
  },
} as HITLGate;

describe('image generation confirmation', () => {
  it('preserves the exact visible image count in the approval payload', () => {
    expect(imageConfirmationDetails(imageGate)).toMatchObject({
      count: 5,
      totalCost: 1,
    });
    expect(approvalPayload(imageGate)).toEqual({
      user_choice: { confirmed_image_count: 5 },
    });
  });
});
