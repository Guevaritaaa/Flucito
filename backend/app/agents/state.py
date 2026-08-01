from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AsistenteState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    cfdi_job_id: NotRequired[str | None]
