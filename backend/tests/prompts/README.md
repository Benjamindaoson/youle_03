# Prompt 回归测试集

任何 `app/config/prompts.py` 修改 → 必须更新此目录下对应 yaml + bump prompt 版本号(治理流程 §6.3)。

格式:每个 prompt 一份 yaml,字段:
```yaml
prompt_name: ORCHESTRATOR_INTENT_PROMPT
version: v1.0.0
cases:
  - name: 反诈视频请求
    input:
      message: "帮我做一个 2026 年的电信诈骗反诈视频"
    expected:
      intent_type: task_request
      domain: video
      scenario: anti_fraud
```

CI 跑 `pytest tests/prompts/` — 全绿才允许 merge。
