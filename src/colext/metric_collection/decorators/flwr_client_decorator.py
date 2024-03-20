import os
import sys 

from typing import Dict
from flwr.common import (Config, Scalar)
from colext.metric_collection.metric_manager import MetricManager
from colext.metric_collection.client_monitor.monitor_manager import MonitorManager
import atexit
from colext.common.logger import log
import logging

# Class inheritence inside a decorator was inspired by:
# https://stackoverflow.com/a/18938008
def MonitorFlwrClient(FlwrClientClass):
    # If we're not under the FL testbed environment, don't make any modifications to the class
    COLEXT_ENV = os.getenv("COLEXT_ENV", 0) 
    if not COLEXT_ENV:
        log.debug(f"Decorator used outside of COLEXT_ENV environment. Not decorating.")
        return FlwrClientClass
        
    log.debug(f"Decorating user Flower client class with Monitor class")
    class MonitorFlwrClient(FlwrClientClass):
        def __init__(self, *args, **kwargs):
            log.debug("init function")
            super().__init__(*args, **kwargs)
            
            self.COLEXT_CLIENT_DB_ID = os.getenv("COLEXT_CLIENT_DB_ID")
            if self.COLEXT_CLIENT_DB_ID == None:
                print(f"Inside CoLExT environment but COLEXT_CLIENT_DB_ID env variable is not defined. Exiting.") 
                sys.exit(1)

            self.metric_mgr: MetricManager = MetricManager()
            self.metric_mgr.start_metric_gathering()

            self.monitor_mgr: MonitorManager = MonitorManager(self.metric_mgr.get_metric_queue())
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
                colext_properties_dict["COLEXT_CLIENT_DB_ID"] = self.COLEXT_CLIENT_DB_ID

            properties = super().get_properties(config)
            if properties is None:
                properties = {}
            properties.update(colext_properties_dict)
            return properties

        def get_parameters(self, config):
            log.debug("get_parameters function")
            return super().get_parameters(config)

        # def set_parameters(self, config):
        def set_parameters(self, *args, **kwargs):
            log.debug("set_parameters function")
            super().set_parameters(*args, **kwargs)

        def fit(self, parameters, config):
            log.debug("fit function")
            return super().fit(parameters, config)

        def evaluate(self, parameters, config):
            log.debug("evaluate function")
            return super().evaluate(parameters, config)
        
    
    return MonitorFlwrClient