import os
import queue
import sys
import time
import multiprocessing
import threading
from colext.common.logger import log
from .client_monitor.scrapper.scrapper_base import ProcessMetrics

import psycopg

class MetricManager():
    def __init__(self, 
                 live_metrics=True,
                 push_metrics_interval=10) -> None:
        self.metric_queue = multiprocessing.Queue()
        self.push_metrics_interval = push_metrics_interval
        self.metrics = []
        self.finish_event = threading.Event()

        self.live_metrics = live_metrics
        self.total_metric_count = 0
        self.metric_push_t = threading.Thread(target=self.push_metrics_live, daemon=True)
        
        self.CLIENT_DB_ID = os.getenv("COLEXT_CLIENT_DB_ID")
        if self.CLIENT_DB_ID == None:
            print(f"Inside CoLExT environment but COLEXT_CLIENT_DB_ID env variable is not defined. Exiting.") 
            sys.exit(1)

    def start_metric_gathering(self):
        log.debug("Start metric monitoring.")
        # Start metric gathering
        self.metric_push_t.start()

    def push_metrics_live(self):
        while(self.finish_event.is_set() is False):
            time.sleep(self.push_metrics_interval)
            self.push_current_metrics()

    def get_metric_queue(self) -> multiprocessing.Queue:
        return self.metric_queue

    def record_metric(self, metric: ProcessMetrics):
        self.metrics.append(metric)

    def collect_available_metrics(self):
        log.debug("Collecting available metrics in the queue.")
        while(True):
            try:
                p_metrics = self.metric_queue.get_nowait()
                self.record_metric(p_metrics)
            except queue.Empty:
                log.debug("Metric queue is empty. Stopping.")
                break

    def stop_metric_gathering(self) -> None:
        log.debug("Shutting down metric manager.")
        if self.live_metrics:
            log.debug("Waiting for background thread to finish. Max 15sec.")
            self.finish_event.set()
            self.metric_push_t.join(timeout=15) 
            if self.metric_push_t.is_alive():
                log.error("Thread is still alive... Ignoring it")

        self.push_current_metrics()
        log.debug(f"Nr of metrics pushed = {self.total_metric_count}.")

    def push_current_metrics(self):
        self.collect_available_metrics()

        #: list[ProcessMetrics]
        metrics = self.metrics

        if len(metrics) == 0:
            log.debug(f"Metric queue was empty. Nothing to push")
            return
        
        log.debug(f"Pushing {len(metrics)} metrics from client {self.CLIENT_DB_ID} to DB")

        DB_CONNECTION_INFO = "host=10.0.0.100 dbname=fl_testbed_db_copy user=faustiar_test_user password=faustiar_test_user"
        INSERT_STRING = """ 
                            INSERT INTO fl_testbed_logging.device_measurements (time, client_id, cpu_util, mem_util, gpu_util, power_consumption) 
                            VALUES (%(time)s, %(client_id)s, %(cpu_util)s, %(mem_util)s, %(gpu_util)s, %(power_consumption)s);
                        """
        
        formatted_metrics = [
            {
                'time': m.time, 
                'client_id': self.CLIENT_DB_ID, 
                'cpu_util': m.cpu_percent, 
                'mem_util': m.rss,
                'gpu_util': m.gpu_util,
                'power_consumption': m.power_mw,
            } 
            for m in metrics]
        
        with psycopg.connect(DB_CONNECTION_INFO) as conn:
            with conn.cursor() as cur:
                cur.executemany(INSERT_STRING, formatted_metrics)
                conn.commit()

        self.total_metric_count += len(metrics)
        self.metrics.clear()