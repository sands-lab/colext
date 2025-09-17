import os
import time
import queue
import threading

from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit
from .scrapers.general_scraper import GeneralScrapper
from .scrapers.scraper_base import ProcessMetrics, ScraperBase

class HWScraper():
    def __init__(self, pid: int, metric_queue: queue.Queue) -> None:
        self.collection_interval_s = float(get_colext_env_var_or_exit("COLEXT_MONITORING_SCRAPE_INTERVAL"))
        log.info(f"Metric collection interval: {self.collection_interval_s}")
        self.metric_queue = metric_queue
        self.pid = pid

        scraperAgent = HWScraper.get_scrapper_agent_for_device()
        self.scrapper = scraperAgent(self.pid, self.collection_interval_s)

        self.finish_event = threading.Event()
        # scraping_loop_th is interrupted using the finish_event
        self.scraping_loop_th = threading.Thread(target=self.scraping_loop, daemon=True)

    def start_scraping(self) -> None:
        self.scraping_loop_th.start()

    def stop_scraping(self) -> None:
        log.info("Stopping HW scraping.")
        self.finish_event.set()
        log.info("Waiting for scraper loop thread. Max 15sec.")
        self.scraping_loop_th.join(timeout=15)
        if self.scraping_loop_th.is_alive():
            log.error("Thread is still alive... Ignoring it")
        log.info("HW scraping stopped")

    def record_metric(self, metric: ProcessMetrics) -> None:
        self.metric_queue.put(metric)

    def scraping_loop(self) -> None:
        while self.finish_event.is_set() is False:
            start_m_time = time.time()
            p_metrics = self.scrapper.scrape_process_metrics()
            self.record_metric(p_metrics)
            stop_m_time = time.time()

            remaining_time = self.collection_interval_s - (stop_m_time - start_m_time)
            remaining_time = max(remaining_time, 0)

            time.sleep(remaining_time)

    @staticmethod
    def get_scrapper_agent_for_device() -> ScraperBase:
        dev_type = get_colext_env_var_or_exit("COLEXT_DEVICE_TYPE")

        scrapper_class = GeneralScrapper # Default

        if "Jetson" in dev_type:
            from .scrapers.jetson_scraper import JetsonScraper
            scrapper_class = JetsonScraper

        return scrapper_class

    @staticmethod
    def has_smart_plug() -> bool:
        return os.getenv("SP_IP_ADDRESS") is not None
