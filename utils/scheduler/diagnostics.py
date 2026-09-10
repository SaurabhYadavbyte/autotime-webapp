from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GenerationDiagnostics:
    status: str
    reason_code: str
    primary_bottleneck: str
    affected_courses: List[str] = field(default_factory=list)
    affected_subjects: List[str] = field(default_factory=list)
    affected_teachers: List[str] = field(default_factory=list)
    required_capacity: int = 0
    available_capacity: int = 0
    shortage: int = 0
    suggestions: List[str] = field(default_factory=list)
    additional_pressure: Optional[str] = None
    bottleneck_stats: dict = field(default_factory=dict)
    statistics: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "primary_bottleneck": self.primary_bottleneck,
            "affected_courses": self.affected_courses,
            "affected_subjects": self.affected_subjects,
            "affected_teachers": self.affected_teachers,
            "required_capacity": self.required_capacity,
            "available_capacity": self.available_capacity,
            "shortage": self.shortage,
            "suggestions": self.suggestions,
            "additional_pressure": self.additional_pressure,
            "bottleneck_stats": self.bottleneck_stats,
            "statistics": self.statistics,
        }


class ReasonCodes:
    INSUFFICIENT_TEACHER_CAPACITY = "INSUFFICIENT_TEACHER_CAPACITY"
    INSUFFICIENT_CLASS_CAPACITY = "INSUFFICIENT_CLASS_CAPACITY"
    TEACHER_AVAILABILITY_CONFLICT = "TEACHER_AVAILABILITY_CONFLICT"
    TEACHER_LEAVE_CONFLICT = "TEACHER_LEAVE_CONFLICT"
    PRACTICAL_SLOT_CONFLICT = "PRACTICAL_SLOT_CONFLICT"
    COMMON_SUBJECT_CONFLICT = "COMMON_SUBJECT_CONFLICT"
    INVALID_SUBJECT_REQUIREMENT = "INVALID_SUBJECT_REQUIREMENT"
    NO_FEASIBLE_ASSIGNMENT = "NO_FEASIBLE_ASSIGNMENT"
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
