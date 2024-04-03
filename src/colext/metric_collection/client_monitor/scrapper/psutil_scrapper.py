from datetime import datetime, timezone
import psutil
from .scrapper_base import ScrapperBase, ProcessMetrics

class PSUtilMonitor(ScrapperBase):
    """
        Base scrapper using psutil.
        This scrapper does not collect power consumption or GPU utilization.
    """
    def __init__(self, pid, collection_interval_s, net_interface="eth0"):
        super().__init__(pid, collection_interval_s)
        self.proc = psutil.Process(pid)

        self.net_interface = net_interface
        self.prev_net_stat = psutil.net_io_counters(pernic=True, nowrap=True)[self.net_interface]
        self.total_bytes_sent = 0
        self.total_bytes_recv = 0
        self.last_scrape_time = datetime.now(timezone.utc)

    def scrape_process_metrics(self) -> ProcessMetrics:
        with self.proc.oneshot():
            cpu_percent = self.proc.cpu_percent()
            rss = self.proc.memory_full_info().rss

        current_net_stat = psutil.net_io_counters(pernic=True, nowrap=True)[self.net_interface]
        n_bytes_sent = current_net_stat.bytes_sent - self.prev_net_stat.bytes_sent
        n_bytes_rcvd = current_net_stat.bytes_recv - self.prev_net_stat.bytes_recv
        self.total_bytes_sent += n_bytes_sent
        self.total_bytes_recv += n_bytes_rcvd
        self.prev_net_stat = current_net_stat

        time = datetime.now(timezone.utc)
        time_between_scrapes = (time - self.last_scrape_time).total_seconds()
        self.last_scrape_time = time

        net_usage_out = round(n_bytes_sent / 1024 / 1024 / time_between_scrapes, 5) # MB/s
        net_usage_in  = round(n_bytes_rcvd / 1024 / 1024 / time_between_scrapes, 5) # MB/s

        power_mw = 0
        gpu_util = 0
        p_metrics = ProcessMetrics(
                        time, cpu_percent, rss, power_mw, gpu_util,
                        self.total_bytes_sent, self.total_bytes_recv, net_usage_out, net_usage_in)
        return p_metrics
    