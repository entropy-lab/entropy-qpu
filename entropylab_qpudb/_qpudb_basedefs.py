import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, auto
from typing import Any

from persistent import Persistent


class CalState(IntEnum):
    UNCAL = auto()
    COARSE = auto()
    MED = auto()
    FINE = auto()

    def __str__(self):
        return self.name


@dataclass(repr=False)
class QpuParameter(Persistent):
    """
    A QPU parameter which stores values and modification status for QPU DB entries
    """

    value: Any
    last_updated: datetime = None
    cal_state: CalState = CalState.UNCAL

    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()

    def __repr__(self):
        if self.value is None:
            return "QpuParameter(None)"
        else:
            return (
                f"QpuParameter(value={self.value}, "
                f"last updated: {self.last_updated.strftime('%m/%d/%Y %H:%M:%S')}, "
                f"calibration state: {self.cal_state})"
            )


FrozenQpuParameter = dataclasses.make_dataclass(
    "FrozenQpuParameter",
    [fld.name for fld in dataclasses.fields(QpuParameter)],
    frozen=True,
)

FrozenQpuParameter.__repr__ = QpuParameter.__repr__
