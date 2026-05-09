from __future__ import annotations

import warnings

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

_ALLOWED_OBJECTS_WARNING = (
    r"The default value of `allowed_objects` will change in a future version\..*"
)


def install_langgraph_warning_filters() -> None:
    warnings.filterwarnings(
        "ignore",
        message=_ALLOWED_OBJECTS_WARNING,
        category=LangChainPendingDeprecationWarning,
        module=r"langgraph\.cache\.base",
    )
