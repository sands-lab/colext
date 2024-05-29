import os
import atexit
import multiprocessing
from typing import Dict
from datetime import datetime, timezone

from flwr.common import (Config, Scalar)

from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit
from colext.metric_collection.metric_manager import MetricManager, StageTimings

# Class inheritence inside a decorator was inspired by:
# https://stackoverflow.com/a/18938008
def MonitorFlwrClient(FlwrClientClass):
    """ Decorator that monitors flwr clients """
    # If we're not under the FL testbed environment, don't make any modifications to the class
    colext_env = os.getenv("COLEXT_ENV", None)
    if not colext_env:
        log.debug("Decorator used outside of COLEXT environment. Not decorating.")
        return FlwrClientClass

    log.debug(f"Decorating user client class ({FlwrClientClass.__name__}) with CoLExt monitor")
    class _MonitorFlwrClient(FlwrClientClass):
        def __init__(self, *args, **kwargs):
            log.debug("init function")
            super().__init__(*args, **kwargs)

            self.client_db_id = get_colext_env_var_or_exit("COLEXT_CLIENT_DB_ID")
            self.client_id = int(get_colext_env_var_or_exit("COLEXT_CLIENT_ID"))

            self.mm_proc_stop_event = multiprocessing.Event()
            self.stage_timings_queue = multiprocessing.Queue()
            self.mm_proc = multiprocessing.Process(
                target=MetricManager_as_bg_process, args=(self.mm_proc_stop_event, self.stage_timings_queue), daemon=True)
            self.mm_proc.start()

            # Replace this, we might be able to cleanup better if the server tells us this is the last round
            atexit.register(self.clean_up)

        def clean_up(self):
            log.debug("Stopping metric manager")
            self.mm_proc_stop_event.set()
            log.info("Waiting for metric manager to finish. Max 15sec.")
            self.mm_proc.join(timeout=15)
            if self.mm_proc.exitcode != 0:
                log.error("Process terminated with non zero exitcode!")
            log.debug("Metric manager stopped")

        # ====== Flower functions ======
        def get_properties(self, config: Config) -> Dict[str, Scalar]:
            log.debug("get_properties function")
            colext_properties_dict = {}
            if "COLEXT_CLIENT_DB_ID" in config:
                colext_properties_dict["COLEXT_CLIENT_DB_ID"] = self.client_db_id

            og_properties = super().get_properties(config)
            return {**colext_properties_dict, **og_properties}

        def get_parameters(self, config):
            log.debug("get_parameters function")
            return super().get_parameters(config)

        # set_parameters is not a function called by flower directly
        # but it's still pretty standard and we could benefit from having it here
        # def set_parameters(self, config):
        def set_parameters(self, *args, **kwargs):
            log.debug("set_parameters function")
            super().set_parameters(*args, **kwargs)

        def fit(self, parameters, config):
            log.debug("fit function")
            client_in_round_id = config[f"COLEXT_CIR_MAP_{self.client_db_id}"]

            start_fit_time = datetime.now(timezone.utc)
            fit_result = super().fit(parameters, config)
            end_fit_time = datetime.now(timezone.utc)

            st = StageTimings(client_in_round_id, "FIT", start_fit_time, end_fit_time)
            self.stage_timings_queue.put(st)

            return fit_result

        def evaluate(self, parameters, config):
            log.debug("evaluate function")
            client_in_round_id = config[f"COLEXT_CIR_MAP_{self.client_db_id}"]

            start_eval_time = datetime.now(timezone.utc)
            eval_result = super().evaluate(parameters, config)
            end_eval_time = datetime.now(timezone.utc)

            st = StageTimings(client_in_round_id, "EVAL", start_eval_time, end_eval_time)
            self.stage_timings_queue.put(st)

            return eval_result

    return _MonitorFlwrClient


def MetricManager_as_bg_process(*args, **kwargs):
    mm = MetricManager(*args, **kwargs)
    # runs until finish_event is set
    mm.start_metric_gathering()
    mm.stop_metric_gathering()
