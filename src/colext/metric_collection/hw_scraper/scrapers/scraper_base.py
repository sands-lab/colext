from abc import ABC, abstractmethod
from colext.metric_collection.typing import ProcessMetrics

class ScraperBase(ABC):
    def __init__(self, pid: int, collection_interval_s: float) -> None:
        self.monitor_pid = pid
        self.collection_interval_s = collection_interval_s

    @abstractmethod
    def scrape_process_metrics(self) -> ProcessMetrics:
        pass