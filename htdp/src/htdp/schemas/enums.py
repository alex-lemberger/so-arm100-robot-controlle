from enum import Enum


class EventLabel(str, Enum):
    START = "start"
    GRASP = "grasp"
    RELEASE = "release"
    PLACE = "place"
    STOP = "stop"


class QcStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class CheckSeverity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ProcessingStatus(str, Enum):
    RAW = "raw"
    PROCESSED = "processed"


class ReleaseProfile(str, Enum):
    INTERNAL_RESEARCH = "internal_research"
    PUBLIC_SAMPLE = "public_sample"
    COMMERCIAL_DATASET = "commercial_dataset"
