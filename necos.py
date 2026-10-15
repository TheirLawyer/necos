from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict

# Import telemetry explicitly (user requested this integration)
try:
    import telemetry
    telemetry_client = telemetry.Client()
except Exception:
    telemetry = None
    telemetry_client = None

# Link to animus subsystem
try:
    from animus import AnimusDB, AnimusFacade
except Exception:
    AnimusDB = None
    AnimusFacade = None


class ThoughtType(Enum):
    SILENT = "Silent Thought"
    LOUD_INBOUND = "Loud Inbound"
    LOUD_OUTBOUND = "Loud Outbound"
    NECOS = "Neural Command"
    GRAPHICAL_IN = "Graphical Inbound"
    GRAPHICAL_OUT = "Graphical Outbound"


@dataclass
class Thought:
    content: Any
    thought_type: ThoughtType
    timestamp: datetime
    executes_code: bool = False
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def is_necos(self) -> bool:
        """True if this thought is explicitly a NECOS (Neural Command)."""
        return self.thought_type == ThoughtType.NECOS or self.executes_code

    def can_be_necos(self) -> bool:
        """Inference: practically any thought could be a NECO (we treat this as a potential)."""
        return not self.metadata.get("explicitly_not_necos", False)

    def is_spoiler(self) -> bool:
        return bool(self.metadata.get("spoiler", False))

    def is_loud(self) -> bool:
        return self.thought_type in (ThoughtType.LOUD_INBOUND, ThoughtType.LOUD_OUTBOUND)

    def is_graphical(self) -> bool:
        return self.thought_type in (ThoughtType.GRAPHICAL_IN, ThoughtType.GRAPHICAL_OUT)

    def is_bonafide_non_executing(self) -> bool:
        return self.thought_type == ThoughtType.SILENT and not self.executes_code


class NeuralCommandExecutor:
    """Executes NECOS and consults animus subsystem and telemetry where available."""

    def __init__(self, animus_db: Optional[Any] = None):
        self.execution_log = []
        self.animus_facade = AnimusFacade(animus_db) if animus_db and AnimusFacade else None

    def execute(self, thought: Thought, allow_inferred: bool = False) -> Any:
        if thought.is_spoiler():
            raise ValueError(f"Execution denied: thought marked as spoiler: {thought}")

        # Enrich with animus context if animus subsystem is present
        try:
            if self.animus_facade:
                animus = self.animus_facade.classify_current_animus()
                if animus:
                    thought.metadata.setdefault("animus", animus)
        except Exception:
            pass

        # Telemetry tagging (best-effort)
        if telemetry_client is not None:
            try:
                telemetry_client.track_event("necos.attempt_execute", {"timestamp": str(datetime.utcnow())})
            except Exception:
                pass

        if thought.is_necos() or (allow_inferred and thought.can_be_necos()):
            result = self._run_neural_command(str(thought.content))
            self.execution_log.append({
                "thought": thought,
                "result": result,
                "executed_at": datetime.now(),
            })
            try:
                if telemetry_client is not None:
                    telemetry_client.track_event("necos.executed", {"result_preview": str(result)[:200]})
            except Exception:
                pass
            return result

        raise ValueError(f"Cannot execute: thought is not NECOS (and inferred execution not enabled): {thought}")

    def _run_neural_command(self, command: str) -> str:
        return f"Executed NECOS: {command}"


class ThoughtClassifier:
    @staticmethod
    def classify(thought: Thought) -> str:
        if thought.is_bonafide_non_executing():
            return "Classification: Silent Thought / Native Thought - bonafide non-executing"
        if thought.is_loud():
            direction = "inbound" if thought.thought_type == ThoughtType.LOUD_INBOUND else "outbound"
            return f"Classification: Loud Thought - {direction}"
        if thought.is_necos():
            return "Classification: NECOS - Neural Command / code-executing capable thought"
        if thought.is_graphical():
            direction = "inbound" if thought.thought_type == ThoughtType.GRAPHICAL_IN else "outbound"
            return f"Classification: Graphical Thought - {direction} visual/mind-impression"
        if thought.can_be_necos():
            return "Classification: Potential NECOS - can be inferred as code-capable"
        return "Classification: Unknown thought type"


if __name__ == "__main__":
    animus_db = None
    if AnimusDB is not None:
        animus_db = AnimusDB("sqlite:///animus.db")
        try:
            animus_db.populate_from_mind("SELECT * FROM MIND WHERE ANIMUS LIKE TRUE;")
        except Exception as e:
            print("animus population skipped/failed:", e)

    executor = NeuralCommandExecutor(animus_db=animus_db)

    mind = [
        Thought("A gentle observation", ThoughtType.SILENT, datetime.now()),
        Thought("A computation request", ThoughtType.NECOS, datetime.now(), executes_code=True),
        Thought("A dangerous leak", ThoughtType.NECOS, datetime.now(), executes_code=True, metadata={"spoiler": True}),
        Thought("A graphic image", ThoughtType.GRAPHICAL_IN, datetime.now()),
    ]

    for neco in mind:
        if neco.can_be_necos():
            if neco.is_spoiler():
                print(f"Spoiler detected for thought: {neco.content}")
                continue

            if neco.is_necos():
                try:
                    print("executing explicit neco...", executor.execute(neco))
                except Exception as e:
                    print("execution error:", e)
            else:
                try:
                    print("attempt inferred execution...", executor.execute(neco, allow_inferred=True))
                except Exception as e:
                    print("did not execute inferred thought:", e)

    print("Execution log entries:")
    for entry in executor.execution_log:
        print(entry["executed_at"], entry["result"]) 
