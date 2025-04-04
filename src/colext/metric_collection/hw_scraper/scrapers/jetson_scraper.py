from .scraper_base import ProcessMetrics
from .general_scraper import GeneralScrapper
from datetime import datetime, timezone
from jtop import jtop
from colext.common.logger import log
import time

class JetsonScraper(GeneralScrapper):
    def __init__(self, pid: int, collection_interval_s: float):
        super().__init__(pid, collection_interval_s)

        # For some reason jetson.gpu returns a list of gpus. We only have 1 so we query it's name and cache it here
        with jtop() as jetson:
            gpu_stats = jetson.gpu
            gpu_list = list(gpu_stats.keys())

            if len(gpu_stats) != 1:
                log.error(f"Expected to find a single gpu with jtop, found = {gpu_stats.keys()}")
                exit(1)

            self.gpu_key = gpu_list[0]

        # 0.15 (magic number) is roughly the time psutils takes to run
        # jtop provides metrics at half of the speed we want
        interval = (collection_interval_s - 0.15) / 2
        log.debug(f"jtop interval = {interval}")
        self.jetson = jtop(interval)
        self.jetson.start()

    def scrape_process_metrics(self) -> ProcessMetrics:
        start_ps_m_time = time.time()
        p_metrics: ProcessMetrics = super().scrape_process_metrics()
        end_ps_m_time = time.time()
        log.debug(f"psutil time = {end_ps_m_time - start_ps_m_time}")

        # jetson.ok is needed to avoid getting stats in an inconsistent state
        # jetson.ok blocks until ready to retrieve new metrics
        # https://rnext.it/jetson_stats/reference/jtop.html#jtop.jtop.ok
        start_jtop_m_time = time.time()
        if not self.jetson.ok():
            log.error("jetson.ok returned false!")

        # Override general metrics
        p_metrics.power_consumption = self.jetson.power["tot"]["power"]
        p_metrics.gpu_util = self.jetson.gpu[self.gpu_key]["status"]["load"]

        end_jtop_m_time = time.time()
        log.debug(f"jtop time = {end_jtop_m_time - start_jtop_m_time}")

        timestamp = datetime.now(timezone.utc)
        p_metrics.time = timestamp
        return p_metrics


    # If we don't close the jtop connection, the jtop service may crash
    def __del__(self):
        if self.jetson:
            log.info("Closing jtop connection")
            self.jetson.close()
            log.info("jtop connection closed")
        else:
            log.info("jtop connection was never established!")
