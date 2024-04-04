import os
import time 
import multiprocessing
from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit
from .scrapper.psutil_scrapper import PSUtilMonitor
from .scrapper.scrapper_base import ProcessMetrics, ScrapperBase

class MonitorAgent():
    def __init__(self, 
                    metric_queue: multiprocessing.Queue,
                    finish_event: multiprocessing.Event,
                    pid: int,
                    collection_interval_s: int) -> None:
        
        self.metric_queue = metric_queue
        self.collection_interval_s = collection_interval_s
        
        Scrapper = get_scrapper_agent_for_dev()
        self.scrapping_agent = Scrapper(pid, self.collection_interval_s)

        # monitor_process is interrupted using the finish_event
        # start monitoring process
        self.monitor_process(finish_event)

    def record_metric(self, metric: ProcessMetrics) -> None:
        self.metric_queue.put(metric)
    
    def monitor_process(self, finish_event) -> None:
        while(finish_event.is_set() is False):
            start_m_time = time.time()
            p_metrics = self.scrapping_agent.scrape_process_metrics()
            self.record_metric(p_metrics)
            stop_m_time = time.time()

            remaining_time = self.collection_interval_s - (stop_m_time - start_m_time)
            if remaining_time < 0:
                remaining_time = 0

            time.sleep(remaining_time)

class MonitorManager():
    def __init__(self, metric_queue: multiprocessing.Queue) -> None:
        # TODO Pass this variable as a parameter to monitor manager
        self.collection_interval_s = float(get_colext_env_var_or_exit("COLEXT_MONITORING_SCRAPE_INTERVAL"))
        log.info(f"Metric collection interval: {self.collection_interval_s}")
        
        self.pid = os.getpid()
        
        self.finish_event = multiprocessing.Event()
        self.m_process = multiprocessing.Process(
            target=MonitorAgent, args=(metric_queue, self.finish_event, self.pid, self.collection_interval_s))
        
    def start_monitoring(self) -> None:
        self.m_process.start()

    def stop_monitoring(self) -> None:
        log.info("Stopping monitoring.")
        self.finish_event.set()
        log.info("Wait for background process to finish. Max 15sec.")
        self.m_process.join(timeout=15) 
        if self.m_process.exitcode != 0:
            log.error("Process terminated with non zero exit!")
        log.info("Monitor stopped")

def get_scrapper_agent_for_dev() -> ScrapperBase:
    uname_release = os.uname().release
    
    scrapper_agent = PSUtilMonitor
    if "tegra" in uname_release:
        from .scrapper.jetson_scapper import JetsonMonitor
        scrapper_agent = JetsonMonitor
    
    return scrapper_agent

if __name__ == '__main__':
    mm = MonitorManager()
    mm.start_monitoring()
    time.sleep(10)
    mm.stop_monitoring()
