from __future__ import annotations

import warnings

from agents.orchestrator_agent.langgraph_compat import install_langgraph_warning_filters
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

_ALLOWED_OBJECTS_WARNING = (
    "The default value of `allowed_objects` will change in a future version. "
    "Pass an explicit value (e.g., allowed_objects='messages' or allowed_objects='core') "
    "to suppress this warning."
)


def test_langgraph_allowed_objects_filter_is_narrow() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        install_langgraph_warning_filters()

        warnings.warn_explicit(
            _ALLOWED_OBJECTS_WARNING,
            LangChainPendingDeprecationWarning,
            filename="/site-packages/langgraph/cache/base/__init__.py",
            lineno=8,
            module="langgraph.cache.base",
        )
        warnings.warn_explicit(
            _ALLOWED_OBJECTS_WARNING,
            LangChainPendingDeprecationWarning,
            filename="/app/other.py",
            lineno=1,
            module="app.other",
        )

    assert len(caught) == 1
    assert caught[0].filename == "/app/other.py"
