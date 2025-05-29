from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import time
import psutil

from colext.common.logger import log
from .smart_plug import SmartPlug
from .scraper_base import ScraperBase, ProcessMetrics


class GeneralScrapper(ScraperBase):
    """
        Base scraper using psutil.
        This scraper tries to collect power consumption using the smart plug plugin.
        It does not capture GPU utilization
    """
    def __init__(self, pid:int , collection_interval_s: float):
        super().__init__(pid, collection_interval_s)
        self.proc = psutil.Process(pid)

        self.prev_net_stat = psutil.net_io_counters(nowrap=True)
        self.total_bytes_sent = 0
        self.total_bytes_recv = 0
        self.last_scrape_time = datetime.now(timezone.utc)

        try:
            self.smart_plug = SmartPlug()
        except ValueError as e:
            log.error(f"Failed to initialize smart plug plugin. Will not use it. {e}")
            self.smart_plug = None

    def scrape_process_metrics(self) -> ProcessMetrics:
        start_scrape_time = time.time()
        if self.smart_plug:
             # Use a ThreadPoolExecutor to run _scrape_psutils and get power concurrently
            with ThreadPoolExecutor() as executor:
                psutils_future = executor.submit(self._scrape_psutils)
                get_power_future = executor.submit(self.smart_plug.get_power_consumption)

                # Wait for both tasks to complete
                p_metrics = psutils_future.result()
                p_metrics.power_consumption = get_power_future.result()
        else:
            p_metrics = self._scrape_psutils()

        end_scrape_time = time.time()
        scrape_duration = end_scrape_time - start_scrape_time
        if scrape_duration > self.collection_interval_s:
            log.warning(f"scrape_process_metrics time exceeded colection interval = {scrape_duration}")

        return p_metrics

    def _scrape_psutils(self) -> ProcessMetrics:
        with self.proc.oneshot():
            cpu_util = self.proc.cpu_percent()
            mem_util = self.proc.memory_full_info().rss

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

        power_consumption = 0
        gpu_util = 0
        p_metrics = ProcessMetrics(
                        current_time, cpu_util, gpu_util, mem_util, power_consumption,
                        self.total_bytes_sent, self.total_bytes_recv, net_usage_out, net_usage_in)
        return p_metrics
