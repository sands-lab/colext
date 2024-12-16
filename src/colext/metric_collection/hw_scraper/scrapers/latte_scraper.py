from datetime import datetime, timezone
import time
import pyRAPL
from colext.common.logger import log
from .scraper_base import ProcessMetrics
from .general_scraper import GeneralScrapper

class LatteScraper(GeneralScrapper):
    def __init__(self, pid: int, collection_interval_s: float):
        super().__init__(pid, collection_interval_s)
        pyRAPL.setup()
        self.p_meter = pyRAPL.Measurement('colext_measurements')
        self.p_meter.begin()

    def scrape_process_metrics(self) -> ProcessMetrics:
        start_ps_m_time = time.time()
        p_metrics: ProcessMetrics = super().scrape_process_metrics()
        end_ps_m_time = time.time()
        log.debug(f"psutil time = {end_ps_m_time - start_ps_m_time}")
        self.p_meter.end()

        energy_mj = self.p_meter.result.pkg[0] / 1.0e3
        interval_sec = self.p_meter.result.duration / 1.0e6
        # Override general metrics
        p_metrics.power_consumption = energy_mj / interval_sec

        timestamp = datetime.now(timezone.utc)
        p_metrics.time = timestamp
        self.p_meter.begin()

        return p_metrics