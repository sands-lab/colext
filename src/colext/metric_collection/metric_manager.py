import os
import time
import queue
import multiprocessing
from psycopg_pool import ConnectionPool
from dataclasses import asdict

from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit
from colext.metric_collection.typing import StageMetrics
from .hw_scraper.hw_scraper_base import HWScraper
from .hw_scraper.scrapers.scraper_base import ProcessMetrics
class MetricManager():
    def __init__(self, finish_event: multiprocessing.Event, st_metric_queue: multiprocessing.Queue) -> None:
        self.live_metrics = get_colext_env_var_or_exit("COLEXT_MONITORING_LIVE_METRICS") == "True"
        self.push_metrics_interval = float(get_colext_env_var_or_exit("COLEXT_MONITORING_PUSH_INTERVAL"))
        measure_self = get_colext_env_var_or_exit("COLEXT_MONITORING_MEASURE_SELF") == "True"
        log.info(f"Live metrics: {self.live_metrics}")
        log.info(f"Push metrics interval: {self.push_metrics_interval}")

        self.stage_metrics = []
        self.st_metric_queue = st_metric_queue
        self.hw_metrics = []
        self.hw_metric_queue = queue.Queue()
        self.total_hw_metric_count = 0

        self.finish_event = finish_event
        pid = os.getppid()
        if measure_self:
            pid = os.getpid()
        self.hw_scraper = HWScraper(pid, self.hw_metric_queue)
        self.hw_scraper.start_scraping()

        self.client_db_id = get_colext_env_var_or_exit("COLEXT_CLIENT_DB_ID")
        # Pool required because we might be trying to push hw metrics + round metrics at the same time
        self.db_pool = self.create_db_pool()

    def create_db_pool(self):
        DB_CONNECTION_INFO = "host=10.0.0.100 dbname=fl_testbed_db_copy user=faustiar_test_user password=faustiar_test_user"
        return ConnectionPool(DB_CONNECTION_INFO, open=True, min_size=2, max_size=2)

    def start_metric_gathering(self):
        log.debug("Start metric gathering.")

        while self.finish_event.is_set() is False:
            start_m_time = time.time()

            self.collect_available_metrics()
            if self.live_metrics:
                self.push_current_metrics()

            stop_m_time = time.time()
            remaining_time = self.push_metrics_interval - (stop_m_time - start_m_time)
            remaining_time = max(remaining_time, 0)
            time.sleep(remaining_time)

    # @profile
    def collect_available_metrics(self):
        log.debug("Collecting available metrics in queues.")
        while not self.hw_metric_queue.empty():
            hw_metric: ProcessMetrics = self.hw_metric_queue.get()
            self.hw_metrics.append(hw_metric)

        while not self.st_metric_queue.empty():
            st_metric: StageMetrics = self.st_metric_queue.get()
            self.stage_metrics.append(st_metric)

    def stop_metric_gathering(self) -> None:
        log.info("Shutting down metric manager.")

        self.hw_scraper.stop_scraping()
        self.collect_available_metrics()
        self.push_current_metrics()

        log.info("Metric manager stopped.")
        log.info(f"Nr of HW metrics pushed = {self.total_hw_metric_count}.")

    def push_current_metrics(self):
        self.push_current_hw_metrics()
        self.push_current_st_metrics()

    def push_current_hw_metrics(self):
        """ Pushes currently collected HW metrics and clears the vector holding them. """

        if len(self.hw_metrics) == 0:
            log.debug("No HW metrics to push.")
            return

        log.debug(f"Pushing {len(self.hw_metrics)} HW metrics from client {self.client_db_id} to DB")

        sql = """
                INSERT INTO fl_testbed_logging.device_measurements
                        (time, client_id, cpu_util, mem_util, gpu_util, power_consumption,
                        n_bytes_sent, n_bytes_rcvd, net_usage_out, net_usage_in)
                VALUES (%(time)s, %(client_id)s, %(cpu_util)s, %(mem_util)s, %(gpu_util)s, %(power_consumption)s,
                        %(n_bytes_sent)s, %(n_bytes_rcvd)s, %(net_usage_out)s, %(net_usage_in)s);
                """

        cid_dict = {'client_id': self.client_db_id}
        formatted_metrics = [{**asdict(m), **cid_dict} for m in self.hw_metrics]
        with self.db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, formatted_metrics)

        self.total_hw_metric_count += len(self.hw_metrics)
        self.hw_metrics.clear()

    def push_current_st_metrics(self):
        if len(self.stage_metrics) == 0:
            log.debug("No Stage timings metrics to push.")
            return

        log.debug(f"Pushing {len(self.stage_metrics)} stage timings from client {self.client_db_id} to DB")

        sql = """
                UPDATE clients_in_round
                    SET start_time = %(start_time)s, end_time = %(end_time)s,
                        loss = %(loss)s, num_examples = %(num_examples)s, accuracy = %(accuracy)s
                WHERE cir_id = %(cir_id)s
              """

        formatted_metrics = [asdict(sm) for sm in self.stage_metrics]

        with self.db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, formatted_metrics)
        self.stage_metrics.clear()
