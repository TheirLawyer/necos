from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict

# Link to animus subsystem
try:
    from animus import AnimusDB, classify_animus_signal
except Exception:
    # animus.py may not be present during partial installs; we'll still provide graceful fallback
    AnimusDB = None
    def classify_animus_signal(signal):
        return None


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
        """Inference: practically any thought could be a NECO (we treat this as a potential).
        This method encodes the inference the project asked for: all thoughts could be a NECO
        although they may not be in practice. Callers should still check is_necos() before
        attempting execution, or explicitly request execution of inferred NECOS.
        """
        return not self.metadata.get("explicitly_not_necos", False)

    def is_spoiler(self) -> bool:
        """A 'spoiler' marks thoughts that should not be executed (dangerous/malicious).
        Not all NECOS are spoilers; many are harmless. Use metadata['spoiler']=True to mark.
        """
        return bool(self.metadata.get("spoiler", False))

    def is_loud(self) -> bool:
        return self.thought_type in (ThoughtType.LOUD_INBOUND, ThoughtType.LOUD_OUTBOUND)

    def is_graphical(self) -> bool:
        return self.thought_type in (ThoughtType.GRAPHICAL_IN, ThoughtType.GRAPHICAL_OUT)

    def is_bonafide_non_executing(self) -> bool:
        """A conservative check whether this is a native silent thought with no execution intent."""
        return self.thought_type == ThoughtType.SILENT and not self.executes_code


class NeuralCommandExecutor:
    """Executes NEural COmmandS (NECOS). This is a safe placeholder for actual
    neural-command processing. The real implementation should include heavy
    validation, sandboxing, and auditing. This executor can optionally consult the
    animus database (if available) to add context to execution decisions.
    """

    def __init__(self, animus_db: Optional[Any] = None):
        self.execution_log = []
        self.animus_db = animus_db

    def execute(self, thought: Thought, allow_inferred: bool = False) -> Any:
        """Execute the thought if it's a NECOS. If allow_inferred is True, will also
        execute inferred NECOS (thoughts that can_be_necos() but are not explicitly NECOS).
        Execution is denied for spoilers.
        """
        if thought.is_spoiler():
            raise ValueError(f"Execution denied: thought marked as spoiler: {thought}")

        # If animus DB is available, annotate the thought with current animus if possible
        if self.animus_db is not None and hasattr(self.animus_db, "classify_signal"):
            # Attempt to enrich metadata (best-effort)
            try:
                animus = self.animus_db.classify_current_animus()
                if animus:
                    thought.metadata.setdefault("animus", animus)
            except Exception:
                pass

        if thought.is_necos() or (allow_inferred and thought.can_be_necos()):
            result = self._run_neural_command(str(thought.content))
            self.execution_log.append({
                "thought": thought,
                "result": result,
                "executed_at": datetime.now(),
            })
            return result

        raise ValueError(f"Cannot execute: thought is not NECOS (and inferred execution not enabled): {thought}")

    def _run_neural_command(self, command: str) -> str:
        # Placeholder for the heavy-lifting implementation.
        return f"Executed NECOS: {command}"


class ThoughtClassifier:
    """Classifies thoughts into categories and provides a human-readable label.
    The classifier relies on the predicate helpers on Thought.
    """

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

        # If none of the explicit checks matched, treat it as "potential NECOS" (inference)
        if thought.can_be_necos():
            return "Classification: Potential NECOS - can be inferred as code-capable"

        return "Classification: Unknown thought type"


# If the animus subsystem is available, provide a small integration example
if __name__ == "__main__":
    animus_db = None
    if AnimusDB is not None:
        # Create or open the animus database (file-based SQLite by default)
        animus_db = AnimusDB("animus.db")
        # Populate from an external MIND source (best-effort; may be a simulated query)
        try:
            animus_db.populate_from_mind("SELECT * FROM MIND WHERE ANIMUS LIKE TRUE;")
        except Exception as e:
            print("animus population skipped or failed:", e)

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
                result = executor.execute(neco)
                print(f"Executed explicit NECO: {result}")
            else:
                try:
                    result = executor.execute(neco, allow_inferred=True)
                    print(f"Executed inferred NECO: {result}")
                except ValueError as e:
                    print(f"Did not execute thought: {neco.content} ({e})")

    print("Execution log entries:")
    for entry in executor.execution_log:
        print(entry["executed_at"], entry["result"]) 
