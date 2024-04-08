import os
from datetime import datetime, timezone
import atexit
from typing import Dict

from flwr.common import (Config, Scalar)

from colext.metric_collection.metric_manager import MetricManager
from colext.metric_collection.client_monitor.monitor_manager import MonitorManager
from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit

# Class inheritence inside a decorator was inspired by:
# https://stackoverflow.com/a/18938008
def MonitorFlwrClient(FlwrClientClass):
    """ Decorator that monitors flwr clients """
    # If we're not under the FL testbed environment, don't make any modifications to the class
    COLEXT_ENV = os.getenv("COLEXT_ENV", 0) 
    if not COLEXT_ENV:
        log.debug(f"Decorator used outside of COLEXT_ENV environment. Not decorating.")
        return FlwrClientClass
        
    log.debug(f"Decorating user Flower client class with Monitor class")
    class _MonitorFlwrClient(FlwrClientClass):
        def __init__(self, *args, **kwargs):
            log.debug("init function")
            super().__init__(*args, **kwargs)
            
            self.client_DB_id = get_colext_env_var_or_exit("COLEXT_CLIENT_DB_ID")
            self.client_id = int(get_colext_env_var_or_exit("COLEXT_CLIENT_ID"))

            self.metric_mgr: MetricManager = MetricManager()
            self.metric_mgr.start_metric_gathering()
            self.monitor_mgr: MonitorManager = MonitorManager(self.metric_mgr.get_hw_metric_queue())
            self.monitor_mgr.start_monitoring()
            
            # Replace this, we might be able to do it if the server tells us this is the last round
            atexit.register(self.clean_up)
        
        def clean_up(self):
            log.debug("Cleaning up monitoring process")
            self.monitor_mgr.stop_monitoring()
            # Metric manager should be terminated after monitor manager
            self.metric_mgr.stop_metric_gathering()


        # ====== Flower functions ======
        def get_properties(self, config: Config) -> Dict[str, Scalar]:
            log.debug("get_properties function")
            colext_properties_dict = {}
            if "COLEXT_CLIENT_DB_ID" in config:
                colext_properties_dict["COLEXT_CLIENT_DB_ID"] = self.client_DB_id

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
            # client_in_round_id = config["COLEXT_CLIENT_IN_ROUND_MAP"][self.client_DB_id]
            client_in_round_id = config.get(f"COLEXT_CIR_MAP_{self.client_DB_id}")
            
            start_fit_time = datetime.now(timezone.utc)
            fit_result = super().fit(parameters, config)
            end_fit_time = datetime.now(timezone.utc)
            self.metric_mgr.push_stage_timings("FIT", client_in_round_id, start_fit_time, end_fit_time)
            return fit_result

        def evaluate(self, parameters, config):
            log.debug("evaluate function")
            # client_in_round_id = config["COLEXT_CLIENT_IN_ROUND_MAP"][self.client_DB_id]
            client_in_round_id = config.get(f"COLEXT_CIR_MAP_{self.client_DB_id}")
            
            start_eval_time = datetime.now(timezone.utc)
            eval_result = super().evaluate(parameters, config)
            end_eval_time = datetime.now(timezone.utc)
            self.metric_mgr.push_stage_timings("EVAL", client_in_round_id, start_eval_time, end_eval_time)

            return eval_result

    return _MonitorFlwrClient
