"""LangGraph 接入(铁律 1 单一调度者的"内核"换装):

把现有的"Skill YAML → DAG → Redis Streams 派发"重写成 LangGraph StateGraph,
保留 Redis Streams 作为分布式 Agent 派发管道,但**编排核心**和**HITL 暂停**改用
LangGraph 原生原语。

关键收益(对比自写 TaskRunner):
1. **PostgresSaver** 自动 checkpoint task state — 直接打通 V2 中断 C/D
   (回滚到第 N 步)= `graph.update_state(checkpoint_id=...)` + `graph.invoke(None)`
2. **interrupt()** 替换 hitl_gate 的"DB closed_at IS NULL + 轮询"模式
3. **Send()** 动态 fan-out:同层并行 step 不再靠 sweep,直接 yield Send
4. **astream_events** 给前端推 token / 中间状态 / 节点开始结束

不动的(继续自写):
- Redis Streams 派发 Agent 任务(分布式优势 > LangGraph in-process 调度)
- Agent worker 消费回执(LangGraph 节点只负责"派发 + 等回执")
- 飞轮 4 类信号 emit(继续走现有 flywheel.py)
"""

from agents.orchestrator_agent.langgraph_compat import install_langgraph_warning_filters

install_langgraph_warning_filters()

from agents.orchestrator_agent.langgraph_runner.compiler import build_state_graph  # noqa: E402
from agents.orchestrator_agent.langgraph_runner.runner import LangGraphTaskRunner  # noqa: E402
from agents.orchestrator_agent.langgraph_runner.state import TaskState  # noqa: E402

__all__ = ["LangGraphTaskRunner", "TaskState", "build_state_graph"]
