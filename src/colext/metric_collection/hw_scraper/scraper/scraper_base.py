from abc import ABC
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ProcessMetrics:
    """Class to keep track of process metrics"""
    time: datetime
    cpu_percent: float
    memory_usage: int
    power_mw: int
    gpu_util: float

    n_bytes_sent: int
    n_bytes_rcvd: int
    net_usage_out: float
    net_usage_in: float

    # temperature: int # jtop.temperature.temp
    # fan_speed: int # jtop.fan.speed

class ScraperBase(ABC):
    def __init__(self, pid: int, collection_interval_s: float) -> None:
        self.monitor_pid = pid

    def scrape_process_metrics(self) -> ProcessMetrics:
        raise NotImplementedError