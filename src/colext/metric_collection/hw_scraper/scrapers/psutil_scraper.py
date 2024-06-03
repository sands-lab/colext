from datetime import datetime, timezone
import psutil
from .scraper_base import ScraperBase, ProcessMetrics

class PSUtilScrapper(ScraperBase):
    """
        Base scraper using psutil.
        This scraper does not collect power consumption or GPU utilization.
    """
    def __init__(self, pid:int , collection_interval_s: float):
        super().__init__(pid, collection_interval_s)
        self.proc = psutil.Process(pid)

        self.prev_net_stat = psutil.net_io_counters(nowrap=True)
        self.total_bytes_sent = 0
        self.total_bytes_recv = 0
        self.last_scrape_time = datetime.now(timezone.utc)

    def scrape_process_metrics(self) -> ProcessMetrics:
        with self.proc.oneshot():
            cpu_percent = self.proc.cpu_percent()
            memory_usage = self.proc.memory_full_info().rss

        current_net_stat = psutil.net_io_counters(nowrap=True)
        n_bytes_sent = current_net_stat.bytes_sent - self.prev_net_stat.bytes_sent
        n_bytes_rcvd = current_net_stat.bytes_recv - self.prev_net_stat.bytes_recv
        self.total_bytes_sent += n_bytes_sent
        self.total_bytes_recv += n_bytes_rcvd
        self.prev_net_stat = current_net_stat

        current_time = datetime.now(timezone.utc)
        time_between_scrapes = (current_time - self.last_scrape_time).total_seconds()
        self.last_scrape_time = current_time

        net_usage_out = round(n_bytes_sent / time_between_scrapes, 5) # B/s
        net_usage_in  = round(n_bytes_rcvd / time_between_scrapes, 5) # B/s

        power_mw = 0
        gpu_util = 0
        p_metrics = ProcessMetrics(
                        current_time, cpu_percent, memory_usage, power_mw, gpu_util,
                        self.total_bytes_sent, self.total_bytes_recv, net_usage_out, net_usage_in)
        return p_metrics
