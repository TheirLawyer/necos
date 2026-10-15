"""
animus.py

Animus subsystem integrated with telemetry, braindecode, hextohuman and optional NN backend.
- Uses SQLAlchemy for database persistence (SQLite by default).
- Imports `telemetry`, `braindecode`, and `hextohuman` as requested (expects them to be installed from PyPI).
- Provides classification pipeline that prefers an NN (torch) if available, falls back to simple rules.
- Exposes populate_from_mind and populate_from_telemetry methods to ingest data.

Security & Ethics: decoding neural signals requires consent, safety, and legal review.
"""
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging
import threading

# Database
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Enum as SAEnum, Text, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker

# Telemetry - required by user; best-effort import
try:
    import telemetry
    telemetry_client = telemetry.Client()
except Exception:
    telemetry = None
    telemetry_client = None

# Brain decoding and translation libraries (assumed installed from PyPI)
try:
    from braindecode import decode_signal
except Exception as e:
    # If these are not available, bubble up later when classification is attempted
    def decode_signal(raw):
        raise RuntimeError("braindecode library not available")

try:
    from hextohuman import translate_decoded
except Exception as e:
    def translate_decoded(intermediate):
        raise RuntimeError("hextohuman library not available")

# Optional NN backend
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False

Base = declarative_base()
LOGGER = logging.getLogger("animus")
LOGGER.setLevel(logging.INFO)


class AnimusClass(Enum):
    PANIMUS = "panimus"       # positive animus
    NANIMUS = "nanimus"       # negative animus
    NEUTRANIMUS = "neutranimus"  # neutral animus


class AnimusType(Base):
    __tablename__ = "animus_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    animus_class = Column(SAEnum(AnimusClass), nullable=False)


class AnimusEntry(Base):
    __tablename__ = "animus_entries"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    animus_type_id = Column(Integer, nullable=False)
    details = Column(Text, nullable=True)
    source = Column(String(256), nullable=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class AnimusDB:
    """Manages Animus DB and ingestion pipelines."""

    def __init__(self, engine_url: str = "sqlite:///animus.db"):
        self.engine = create_engine(engine_url, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self._lock = threading.Lock()
        self._ensure_seed_types()

    def _ensure_seed_types(self):
        with self.SessionLocal() as session:
            existing = session.query(AnimusType).count()
            if existing == 0:
                seed = [
                    AnimusType(name="animus_furandi", description="intent to steal", animus_class=AnimusClass.NANIMUS),
                    AnimusType(name="animus_et_corpore", description="intent regarding body/corporeal", animus_class=AnimusClass.NANIMUS),
                    AnimusType(name="animus_felonicus", description="felonious intent", animus_class=AnimusClass.NANIMUS),
                    AnimusType(name="animus_malus", description="malicious intent", animus_class=AnimusClass.NANIMUS),
                    AnimusType(name="animus_benevolus", description="benevolent intent", animus_class=AnimusClass.PANIMUS),
                    AnimusType(name="animus_neutralis", description="neutral/ambiguous intent", animus_class=AnimusClass.NEUTRANIMUS),
                ]
                session.add_all(seed)
                session.commit()
                LOGGER.info("Seed animus types added")

    def add_entry(self, name: str, animus_type_name: str, details: Optional[str] = None, source: Optional[str] = None):
        with self._lock, self.SessionLocal() as session:
            animus_type = session.query(AnimusType).filter_by(name=animus_type_name).first()
            if not animus_type:
                raise ValueError(f"Unknown animus type: {animus_type_name}")
            entry = AnimusEntry(
                name=name,
                animus_type_id=animus_type.id,
                details=details or "",
                source=source or "unknown"
            )
            session.add(entry)
            session.commit()
            return entry

    def list_entries(self) -> List[AnimusEntry]:
        with self.SessionLocal() as session:
            return session.query(AnimusEntry).all()

    def populate_from_mind(self, sql_query: str, mind_db_url: Optional[str] = None):
        """Populate animus entries from a MIND database using a SELECT query.
        Best-effort mapping; unknown types are mapped to animus_neutralis.
        """
        import sqlite3
        target = mind_db_url or "mind.db"
        try:
            filename = target.replace("sqlite:///", "") if target.startswith("sqlite:///") else target
            conn = sqlite3.connect(filename)
            cur = conn.cursor()
            cur.execute(sql_query)
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else []
            added = 0
            for r in rows:
                row = dict(zip(cols, r))
                name = row.get("animus_name") or row.get("name") or "unknown_animus_entry"
                animus_type_guess = (row.get("animus_type") or row.get("type") or "animus_neutralis").lower().replace(" ", "_")
                try:
                    self.add_entry(name=name, animus_type_name=animus_type_guess, details=str(row), source=filename)
                    added += 1
                except Exception:
                    try:
                        self.add_entry(name=name, animus_type_name="animus_neutralis", details=str(row), source=filename)
                        added += 1
                    except Exception as e:
                        LOGGER.debug("Failed to add animus row: %s", e)
            conn.close()
            LOGGER.info("Populated %d animus entries from %s", added, filename)
            return added
        except Exception as e:
            LOGGER.warning("Failed to populate from MIND database (%s): %s", target, e)
            raise

    def populate_from_telemetry(self, selector: Optional[Dict[str, Any]] = None, limit: int = 100):
        """Attempt to read recent signals from the telemetry client and classify them into animus entries."""
        if telemetry_client is None:
            raise RuntimeError("telemetry client not available")
        added = 0
        # This relies on the telemetry client exposing an API to stream or return recent signals
        get_signals = getattr(telemetry_client, "recent_signals", None)
        if get_signals is None:
            raise RuntimeError("telemetry client does not expose recent_signals() API")
        signals = get_signals(limit=limit, selector=selector or {})
        for s in signals:
            try:
                decoded = decode_signal(s)
                human = translate_decoded(decoded)
                # naive name & type inference
                name = getattr(s, "id", str(datetime.utcnow()))
                text = str(human)
                # classify via simple rule or NN
                cls = _classify_text_to_animus(text)
                animus_type_name = _animus_class_to_type_name(cls)
                self.add_entry(name=name, animus_type_name=animus_type_name, details=text, source="telemetry")
                added += 1
            except Exception as e:
                LOGGER.debug("Failed to process telemetry signal: %s", e)
        LOGGER.info("Populated %d animus entries from telemetry", added)
        return added

    def query(self, sql: str) -> List[Dict[str, Any]]:
        with self.SessionLocal() as session:
            res = session.execute(sql)
            return [dict(row._mapping) for row in res]


# Classification pipeline

def _simple_rule_classifier(text: str) -> AnimusClass:
    t = text.lower()
    neg_keywords = ("steal", "kill", "harm", "felon", "malice", "murder", "rob")
    pos_keywords = ("help", "aid", "assist", "protect", "benevol")
    if any(k in t for k in neg_keywords):
        return AnimusClass.NANIMUS
    if any(k in t for k in pos_keywords):
        return AnimusClass.PANIMUS
    return AnimusClass.NEUTRANIMUS


if TORCH_AVAILABLE:
    class TinyNN(nn.Module):
        def __init__(self, input_dim: int = 32, hidden: int = 64, out_classes: int = 3):
            super().__init__()
            self.fc1 = nn.Linear(input_dim, hidden)
            self.fc2 = nn.Linear(hidden, out_classes)

        def forward(self, x):
            x = F.relu(self.fc1(x))
            return self.fc2(x)

    def _vectorize_text(text: str, dim: int = 32):
        v = torch.zeros(dim, dtype=torch.float32)
        if not text:
            return v
        for i, ch in enumerate(text[:dim]):
            v[i] = (ord(ch) % 97) / 97.0
        return v


def _classify_text_to_animus(text: str) -> AnimusClass:
    if TORCH_AVAILABLE:
        try:
            vec = _vectorize_text(text)
            model = TinyNN(input_dim=vec.shape[0])
            logits = model(vec.unsqueeze(0))
            prob = F.softmax(logits, dim=1).detach().cpu().numpy().squeeze()
            idx = int(prob.argmax())
            return (AnimusClass.PANIMUS, AnimusClass.NANIMUS, AnimusClass.NEUTRANIMUS)[idx]
        except Exception:
            return _simple_rule_classifier(text)
    else:
        return _simple_rule_classifier(text)


def _animus_class_to_type_name(cls: AnimusClass) -> str:
    # Map broad class to an existing seeded animus type
    if cls == AnimusClass.PANIMUS:
        return "animus_benevolus"
    if cls == AnimusClass.NANIMUS:
        return "animus_malus"
    return "animus_neutralis"


# Facade used by necos
class AnimusFacade:
    def __init__(self, db: AnimusDB):
        self.db = db

    def classify_current_animus(self) -> Optional[str]:
        if telemetry_client is None:
            return None
        if not hasattr(telemetry_client, "current_signal"):
            return None
        try:
            signal = telemetry_client.current_signal()
            decoded = decode_signal(signal)
            human = translate_decoded(decoded)
            cls = _classify_text_to_animus(str(human))
            return cls.value
        except Exception as e:
            LOGGER.debug("Failed to classify current animus: %s", e)
            return None
