import os
import atexit
import multiprocessing
from datetime import datetime, timezone

from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit
from colext.metric_collection.metric_manager import MetricManager
from colext.metric_collection.typing import StageMetrics
import subprocess
from network_manager import NetworkManager , NetworkPubSub


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

            self.client_db_id = get_colext_env_var_or_exit("COLEXT_CLIENT_DB_ID")
            self.client_id = int(get_colext_env_var_or_exit("COLEXT_CLIENT_ID"))

            self.mm_proc_stop_event = multiprocessing.Event()
            mm_proc_ready_event = multiprocessing.Event()
            self.stage_timings_queue = multiprocessing.Queue()
            self.mm_proc = multiprocessing.Process(
                target=MetricManager_as_bg_process, args=(self.mm_proc_stop_event, mm_proc_ready_event, self.stage_timings_queue), daemon=True)
            self.mm_proc.start()
            # Wait for metric manager to finish startup
            mm_proc_ready_event.wait()
            
            # Network setup
            net_mngr = NetworkManager()
            #Parse static rules and create the generators
            #static
            net_mngr.ParseStaticRules("network/networkrules.txt")
            #dynamic
            net_mngr.ParseDynamicRules()


            


            # We might be able to cleanup better if the server tells us this is the last round
            atexit.register(self.clean_up)

            # Finish setup before invoking the original constructor
            super().__init__(*args, **kwargs)

        def clean_up(self):
            log.debug("Stopping metric manager")
            self.mm_proc_stop_event.set()
            log.info("Waiting for metric manager to finish. Max 15sec.")
            self.mm_proc.join(timeout=15)
            if self.mm_proc.exitcode != 0:
                log.error("Process terminated with non zero exitcode!")
            log.debug("Metric manager stopped")

        # ====== Flower functions ======
        def fit(self, parameters, config):
            """ Runs the fit or train function of the client """

            log.debug("fit function")
            round_id = config["COLEXT_ROUND_ID"]

            start_fit_time = datetime.now(timezone.utc)
            fit_result = super().fit(parameters, config)
            end_fit_time = datetime.now(timezone.utc)

            num_examples = fit_result[1]
            loss = fit_result[2].get("loss")
            acc = fit_result[2].get("accuracy")
            st = StageMetrics(self.client_db_id, round_id,
                              start_fit_time, end_fit_time, loss, num_examples, acc)
            self.stage_timings_queue.put(st)

            return fit_result

        def evaluate(self, parameters, config):
            """ Runs the evaluate function of the client """

            log.debug("evaluate function")
            round_id = config["COLEXT_ROUND_ID"]

            start_eval_time = datetime.now(timezone.utc)
            eval_result = super().evaluate(parameters, config)
            end_eval_time = datetime.now(timezone.utc)

            loss = eval_result[0]
            num_examples = eval_result[1]
            acc = eval_result[2].get("accuracy")
            st = StageMetrics(self.client_db_id, round_id,
                              start_eval_time, end_eval_time, loss, num_examples, acc)
            self.stage_timings_queue.put(st)

            return eval_result

        # def get_properties(self, config: Config) -> Dict[str, Scalar]:
        #     log.debug("get_properties function")
        #     return super().get_properties(config)

        # get/set_parameters are not functions called by flower directly
        # but they're still pretty standard and we could benefit from having them here
        # def get_parameters(self, *args, **kwargs):
        #     log.debug("get_parameters function")
        #     return super().get_parameters(config)
        # def set_parameters(self, *args, **kwargs):
        #     log.debug("set_parameters function")
        #     super().set_parameters(*args, **kwargs)

    return _MonitorFlwrClient


def MetricManager_as_bg_process(*args, **kwargs):
    mm = MetricManager(*args, **kwargs)

    # runs until finish_event is set
    mm.start_metric_gathering()
    mm.stop_metric_gathering()
