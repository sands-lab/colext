from dataclasses import dataclass
from datetime import datetime
import queue
import time
import multiprocessing
import threading
import psycopg
from psycopg_pool import ConnectionPool

from colext.common.utils import get_colext_env_var_or_exit
from colext.common.logger import log
from .client_monitor.scrapper.scrapper_base import ProcessMetrics

@dataclass
class StageTimings:
    """ Class to keep track of stage(fit/eval) start and end timings"""
    stage: str
    start_time: datetime
    end_time: datetime

class MetricManager():
    def __init__(self) -> None:
        # TODO Pass this variables as parameters to metric manager
        self.live_metrics = get_colext_env_var_or_exit("COLEXT_MONITORING_LIVE_METRICS") == "True"
        self.push_metrics_interval = float(get_colext_env_var_or_exit("COLEXT_MONITORING_PUSH_INTERVAL"))
        log.info(f"Live metrics: {self.live_metrics}")
        log.info(f"Push metrics interval: {self.push_metrics_interval}")
        
        self.hw_metric_queue = multiprocessing.Queue()
        self.hw_metrics = []

        self.total_hw_metric_count = 0
        self.metric_push_th = threading.Thread(target=self.capture_metrics, daemon=True)
        self.finish_event = threading.Event()
        
        self.CLIENT_DB_ID = get_colext_env_var_or_exit("COLEXT_CLIENT_DB_ID")
        self.db_pool = self.create_db_pool()

    def create_db_pool(self):
        DB_CONNECTION_INFO = "host=10.0.0.100 dbname=fl_testbed_db_copy user=faustiar_test_user password=faustiar_test_user"
        return ConnectionPool(DB_CONNECTION_INFO, open=True, min_size=2, max_size=2)

    def start_metric_gathering(self):
        log.debug("Start metric monitoring.")
        self.metric_push_th.start()

    def capture_metrics(self):
        while(self.finish_event.is_set() is False):
            time.sleep(self.push_metrics_interval)
            self.collect_available_metrics()
            if self.live_metrics:
                self.push_current_hw_metrics()

    def get_hw_metric_queue(self) -> multiprocessing.Queue:
        return self.hw_metric_queue

    def record_metric(self, hw_metrics: ProcessMetrics):
        self.hw_metrics.append(hw_metrics)

    def collect_available_metrics(self):
        log.debug("Collecting available metrics in the queue.")
        while(True):
            try:
                hw_metrics = self.hw_metric_queue.get_nowait()
                self.record_metric(hw_metrics)
            except queue.Empty:
                log.debug("Metric queue is empty. Stopping.")
                break

    def stop_metric_gathering(self) -> None:
        log.info("Shutting down metric manager.")
        if self.live_metrics:
            log.info("Waiting for background thread to finish. Max 15sec.")
            self.finish_event.set()
            self.metric_push_th.join(timeout=15) 
            if self.metric_push_th.is_alive():
                log.error("Thread is still alive... Ignoring it")
        
        self.collect_available_metrics()
        self.push_current_hw_metrics()
        log.info(f"Nr of metrics pushed = {self.total_hw_metric_count}.")


    def push_current_hw_metrics(self):
        if len(self.hw_metrics) == 0:
            log.debug(f"No HW metrics to push.")
            return
        
        log.info(f"Pushing {len(self.hw_metrics)} HW metrics from client {self.CLIENT_DB_ID} to DB")

        sql = """ 
                INSERT INTO fl_testbed_logging.device_measurements 
                        (time, client_id, cpu_util, mem_util, gpu_util, power_consumption,
                        n_bytes_sent, n_bytes_rcvd, net_usage_out, net_usage_in) 
                VALUES (%(time)s, %(client_id)s, %(cpu_util)s, %(mem_util)s, %(gpu_util)s, %(power_consumption)s,
                        %(n_bytes_sent)s, %(n_bytes_rcvd)s, %(net_usage_out)s, %(net_usage_in)s);
                """
        
        formatted_metrics = [
            {
                'time': m.time, 
                'client_id': self.CLIENT_DB_ID, 
                'cpu_util': m.cpu_percent, 
                'mem_util': m.rss,
                'gpu_util': m.gpu_util,
                'power_consumption': m.power_mw,
                'n_bytes_sent': m.n_bytes_sent, 
                'n_bytes_rcvd': m.n_bytes_rcvd, 
                'net_usage_out': m.net_usage_out, 
                'net_usage_in': m.net_usage_in
            }
            for m in self.hw_metrics]
        
        with self.db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, formatted_metrics)

        self.total_hw_metric_count += len(self.hw_metrics)
        self.hw_metrics.clear()

    def push_stage_timings(self, stage, cir_id: int, stage_start_time: datetime, stage_end_time: datetime):
        log.info(f"Pushing stage timings for cir_id = {cir_id} stage = {stage}")

        sql = """
                UPDATE clients_in_round 
                    SET start_time = %s, end_time = %s
                WHERE cir_id = %s
              """     
        
        data = (stage_start_time, stage_end_time, cir_id)
        with self.db_pool.connection() as conn:
            conn.execute(sql, data)
        
