"""The one in-memory checkpointer every test and eval builds: the app's strict serde (R15), so a
test rebuilds `sagaloom.models` classes exactly as the runtime saver does, with no langgraph
"Deserializing unregistered type" warning. Importable as `checkpointers` (tests/ is on sys.path
through its rootdir conftest)."""

from langgraph.checkpoint.memory import InMemorySaver

from sagaloom.graph.build import checkpoint_serde


def memory_checkpointer() -> InMemorySaver:
    return InMemorySaver(serde=checkpoint_serde())
