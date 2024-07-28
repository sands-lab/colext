"""Metric collection type definitions."""

from dataclasses import dataclass
from datetime import datetime

@dataclass
class StageMetrics:
    """ Class to keep track of stage(fit/eval) metrics."""

    cir_id: int
    stage: str
    start_time: datetime
    end_time: datetime
    loss: float
    num_examples: int
    accuracy: float

@dataclass
class ProcessMetrics:
    """Class to keep track of process metrics."""

    time: datetime
    cpu_util: float
    gpu_util: float
    mem_util: float
    power_consumption: float

    n_bytes_sent: int
    n_bytes_rcvd: int
    net_usage_out: float
    net_usage_in: float

    # temperature: int # jtop.temperature.temp
    # fan_speed: int # jtop.fan.speed