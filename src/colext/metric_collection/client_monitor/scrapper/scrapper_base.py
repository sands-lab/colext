from abc import ABC
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ProcessMetrics:
    """Class to keep track of process metrics"""
    time: datetime
    cpu_percent: float
    rss: int
    power_mw: int
    gpu_util: float
    # temperature: int # jtop.temperature.temp
    # fan_speed: int # jtop.fan.speed

class ScrapperBase(ABC):
    def __init__(self, pid) -> None:
        self.monitor_pid = pid

    def scrape_process_metrics(self) -> ProcessMetrics:
        raise NotImplementedError