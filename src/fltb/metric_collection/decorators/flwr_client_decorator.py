import os
import sys 

from typing import Dict
from flwr.common import (Config, Scalar)
from fltb.metric_collection.metric_manager import MetricManager
from fltb.metric_collection.client_monitor.monitor_manager import MonitorManager
import atexit
from fltb.common.logger import log

# Class inheritence inside a decorator was inspired by:
# https://stackoverflow.com/a/18938008
def MonitorFlwrClient(FlwrClientClass):
    # If we're not under the FL testbed environment, don't make any modifications to the class
    FLTB_ENV = os.getenv("FLTB_ENV", 0) 
    if not FLTB_ENV:
        log.debug(f"Decorator used outside of FLTB_ENV environment. Not decorating.")
        return FlwrClientClass
        
    log.debug(f"Decorating user Flower client class with Monitor class")
    class MonitorFlwrClient(FlwrClientClass):
        def __init__(self, *args, **kwargs):
            log.debug("init function")
            super().__init__(*args, **kwargs)
            
            self.FLTB_CLIENT_DB_ID = os.getenv("FLTB_CLIENT_DB_ID")
            if self.FLTB_CLIENT_DB_ID == None:
                print(f"Tried to use FL testbed but FLTB_CLIENT_DB_ID env variable is not defined. Exiting.") 
                sys.exit(1)

            self.metric_mgr: MetricManager = MetricManager()
            metric_queue = self.metric_mgr.get_metric_queue()

            self.monitor_mgr: MonitorManager = MonitorManager(metric_queue)
            self.monitor_mgr.start_monitoring()
            # Replace this, we might be able to do it if the server tells us this is the last round
            atexit.register(self.clean_up)
        
        def clean_up(self):
            log.debug("Cleaning up monitoring process")
            self.monitor_mgr.stop_monitoring()
            # Metric manager should be terminated after monitor manager
            self.metric_mgr.shutdown()

        # ====== Flower functions ======
        def get_properties(self, config: Config) -> Dict[str, Scalar]:
            properties_dict = {}
            if "FLTB_CLIENT_DB_ID" in config:
                properties_dict["FLTB_CLIENT_DB_ID"] = self.FLTB_CLIENT_DB_ID
            
            return properties_dict

        def get_parameters(self, config):
            log.debug("get_parameters function")
            return super().get_parameters(config)

        def set_parameters(self, parameters):
            log.debug("set_parameters function")
            super().set_parameters(parameters)

        def fit(self, parameters, config):
            log.debug("fit function")
            return super().fit(parameters, config)

        def evaluate(self, parameters, config):
            log.debug("evaluate function")
            return super().evaluate(parameters, config)
        
    
    return MonitorFlwrClient