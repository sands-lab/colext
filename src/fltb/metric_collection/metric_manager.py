import os
import queue
import sys
import multiprocessing
from fltb.common.logger import log
from .client_monitor.scrapper.scrapper_base import ProcessMetrics

import psycopg

class MetricManager():
    def __init__(self) -> None:
        self.metric_queue = multiprocessing.JoinableQueue()
        self.wait_for_queue_value_sec = 0.5

        self.metrics = []
        
        self.CLIENT_DB_ID = os.getenv("FLTB_CLIENT_DB_ID")
        if self.CLIENT_DB_ID == None:
            print(f"Tried to use FL testbed but CLIENT_DB_ID env variable is not defined. Exiting.") 
            sys.exit(1)

    def start(self):
        self.queue_process.start()

    def get_metric_queue(self) -> multiprocessing.Queue:
        return self.metric_queue

    def record_metric(self, metric: ProcessMetrics):
        self.metrics.append(metric)

    def collect_metrics(self):
        while(True):
            try:
                p_metrics = self.metric_queue.get_nowait()
                self.record_metric(p_metrics)
                self.metric_queue.task_done()
            except queue.Empty:
                log.debug("queue is empty. Stopping")
                break

    def shutdown(self) -> None:
        log.debug("Shutting down metric manager.")
        
        log.debug("Collecting all metrics in the queue.")
        self.collect_metrics()
        self.push_and_clear_collected_metrics()
        log.debug("Metrics have been pushed.")

    def push_and_clear_collected_metrics(self):
        #: list[ProcessMetrics]
        metrics = self.metrics
        
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
        
        self.metrics.clear()