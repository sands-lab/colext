import os
import time 
import multiprocessing
from colext.common.logger import log
from .scrapper.psutil_scrapper import PSUtilMonitor
from .scrapper.scrapper_base import ProcessMetrics, ScrapperBase

class MonitorAgent():
    def __init__(self, 
                    metric_queue: multiprocessing.Queue,
                    finish_event: multiprocessing.Event,
                    pid: int,
                    collection_interval_s: int) -> None:
        
        self.finish_event = finish_event
        self.collection_interval_s = collection_interval_s
        self.metric_queue = metric_queue
        self.scrapping_agent = get_scrapper_agent_for_dev(pid)

        # start monitoring process
        # monitor_process is interrupted using the finish_event
        self.monitor_process()

    def record_metric(self, metric: ProcessMetrics) -> None:
        self.metric_queue.put(metric)
    
    def monitor_process(self) -> None:
        while(self.finish_event.is_set() is False):
            p_metrics = self.scrapping_agent.scrape_process_metrics()
            self.record_metric(p_metrics)
            time.sleep(self.collection_interval_s)


class MonitorManager():
    def __init__(self, metric_queue: multiprocessing.Queue, collection_interval_s = 0.1) -> None:
        self.pid = os.getpid()
        self.finish_event = multiprocessing.Event()
        self.collection_interval_s = collection_interval_s
        self.metric_queue = metric_queue
        self.process = multiprocessing.Process(
            target=MonitorAgent, args=(self.metric_queue, self.finish_event,self.pid, self.collection_interval_s))

    def start_monitoring(self):
        self.process.start()

    def stop_monitoring(self):
        log.debug("Stopping monitoring.")
        self.finish_event.set()
        log.debug("Wait for background process to finish. Max 10sec.")
        self.process.join(timeout=10) 
        if self.process.exitcode != 0:
            log.debug("Process terminated with non zero exit!")
        log.debug("Monitor stopped")

def get_scrapper_agent_for_dev(pid) -> ScrapperBase:
    uname_release = os.uname().release
    
    scrapper_agent = PSUtilMonitor
    if "tegra" in uname_release:
        from .scrapper.jetson_scapper import JetsonMonitor
        scrapper_agent = JetsonMonitor
    
    return scrapper_agent(pid)

if __name__ == '__main__':
    mm = MonitorManager()
    mm.start_monitoring()
    time.sleep(10)
    mm.stop_monitoring()
