from enum import StrEnum


class MemoryKind(StrEnum):
    STORYLINE = "storyline"
    FACT = "fact"
    EVENT = "event"
    TRIGGER = "trigger"
    CONTEXT_NOTE = "context_note"
