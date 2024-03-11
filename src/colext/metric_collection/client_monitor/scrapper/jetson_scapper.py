# import jtop
from .scrapper_base import ScrapperBase, ProcessMetrics
from datetime import datetime, timezone
import psutil
from jtop import jtop
from colext.common.logger import log

class JetsonMonitor(ScrapperBase):
    def __init__(self, pid):
        super().__init__(pid)
        self.p = psutil.Process(pid)

        # For some reason jetson.gpu returns a list of gpus. We only have 1 so we query it's name and cache it here
        with jtop() as jetson:
            gpu_stats = jetson.gpu
            gpu_list = list(gpu_stats.keys())
            
            if len(gpu_stats) != 1:
                log.error(f"Expected to find a single gpu with jtop, found = {gpu_stats.keys()}")
                exit(1)
            
            self.gpu_key = gpu_list[0]

    def scrape_process_metrics(self) -> ProcessMetrics:
        with self.p.oneshot():
            cpu_percent = self.p.cpu_percent()
            rss = self.p.memory_full_info().rss

        with jtop() as jetson:
            # This method is needed when you start jtop using with
            # Otherwise we risk trying to get stats in an inconsistent state
            # https://rnext.it/jetson_stats/reference/jtop.html#jtop.jtop.ok
            if jetson.ok():
                power_mw = jetson.power["tot"]["power"]
                gpu_util = jetson.gpu[self.gpu_key]["status"]["load"]
            
        time = datetime.now(timezone.utc)
        p_metrics = ProcessMetrics(time, cpu_percent, rss, power_mw, gpu_util)
        return p_metrics