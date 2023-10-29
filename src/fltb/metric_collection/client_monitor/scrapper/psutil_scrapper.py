# import psutil
from datetime import datetime, timezone
import psutil
from .scrapper_base import ScrapperBase, ProcessMetrics

class PSUtilMonitor(ScrapperBase):
    def __init__(self, pid):
        super().__init__(pid)
        self.p = psutil.Process(pid)

    def scrape_process_metrics(self) -> ProcessMetrics:
        with self.p.oneshot():
            cpu_percent = self.p.cpu_percent()
            rss = self.p.memory_full_info().rss

        time = datetime.now(timezone.utc)
        p_metrics = ProcessMetrics(time, cpu_percent, rss, power_mw=0, gpu_util=0)
        return p_metrics