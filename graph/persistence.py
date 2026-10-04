from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from graph.workflow import build_workflow


DEFAULT_CHECKPOINT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "checkpoints.db"
)


@contextmanager
def persistent_workflow(
    store,
    checkpoint_path=DEFAULT_CHECKPOINT_PATH,
    **agents,
):
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        graph = build_workflow(
            store,
            checkpointer=saver,
            **agents,
        )
        yield graph