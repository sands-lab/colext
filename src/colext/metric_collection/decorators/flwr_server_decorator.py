import os
import re
import atexit
import psycopg
from colext.common.logger import log

from typing import List, Tuple, Union, Optional, Dict
from flwr.common import (
    FitIns, Parameters, FitRes, Scalar, EvaluateIns, EvaluateRes, GetPropertiesIns, GetPropertiesRes, Code
)
from flwr.server.client_manager import ClientManager
from flwr.server.client_proxy import ClientProxy

# Class inheritence inside a decorator was inspired by:
# https://stackoverflow.com/a/18938008
def MonitorFlwrStrategy(FlwrStrategy):
    COLEXT_ENV = os.getenv("COLEXT_ENV", 0) 
    if not COLEXT_ENV:
        log.debug(f"Decorator used outside of COLEXT_ENV environment. Not decorating.")
        return FlwrStrategy
    
    log.debug(f"Decorating user Flower server class with Monitor class")
    class MonitorFlwrStrategy(FlwrStrategy):
        def __init__(self, *args, **kwargs):
            log.debug("init function")
            super().__init__(*args, **kwargs)

            self.JOB_ID = os.getenv("COLEXT_JOB_ID")
            if self.JOB_ID == None:
                print(f"Inside CoLExT environment but COLEXT_JOB_ID env variable is not defined. Exiting.") 
                exit(1)
            
            self.DB_CONNECTION = self.create_db_connection()
            self.clients_ip_to_id = {}

        def create_db_connection(self):
            DB_CONNECTION_INFO = "host=10.0.0.100 dbname=fl_testbed_db_copy user=faustiar_test_user password=faustiar_test_user"
            return psycopg.connect(DB_CONNECTION_INFO)

        def record_new_round(self, server_round: int, round_type: str):
            cursor = self.DB_CONNECTION.cursor()

            sql = "INSERT INTO fl_testbed_logging.rounds(round_number, start_time, job_id, fit_eval) \
                    VALUES (%s, CURRENT_TIMESTAMP, %s, %s) returning round_id"
            data = (str(server_round), str(self.JOB_ID), round_type)
            cursor.execute(sql, data)
            ROUND_ID = cursor.fetchone()[0]

            cursor.close()

            return ROUND_ID
        
        def get_client_db_id(self, client_proxy: ClientProxy) -> int:
            ip_address = re.search(r'ipv4:(\d+\.\d+\.\d+\.\d+):\d+', client_proxy.cid.__str__()).group(1)
            if ip_address is None:
                log.error("Could not parse IP for client. Client IP = {ip_address}")

            if ip_address not in self.clients_ip_to_id:
                # Client ip not mapped to client id. Ask client for id
                # Not sure how the timeout works
                properties_res: GetPropertiesRes = client_proxy.get_properties(GetPropertiesIns(config={"COLEXT_CLIENT_DB_ID": "?"}), timeout=3)
                assert properties_res.status.code == Code.OK
                client_id = properties_res.properties["COLEXT_CLIENT_DB_ID"]
                self.clients_ip_to_id[ip_address] = client_id

            return self.clients_ip_to_id[ip_address]

        def configure_clients_in_round(self, client_instructions: List[Tuple[ClientProxy, FitIns]], round_id: int) -> List[Tuple[ClientProxy, FitIns]]:
            cursor = self.DB_CONNECTION.cursor()

            # Register clients in round
            sql = "INSERT INTO fl_testbed_logging.clients_in_rounds (client_id, round_id, client_state) \
                    VALUES (%s, %s, %s) returning cir_id"
            for (proxy, fit_ins) in client_instructions:  # First (ClientProxy, FitIns) pair
                client_db_id = self.get_client_db_id(proxy)
                
                cur_client_state = "AVAILABLE"
                data = (client_db_id, str(round_id), cur_client_state)
                cursor.execute(sql, data)
                cir_id = cursor.fetchone()[0]

                fit_ins.config["CIR_ID"] = cir_id

            self.DB_CONNECTION.commit()
            cursor.close()

            return client_instructions 
    
        # ====== Flower functions ======

        def configure_fit(self, server_round: int, parameters: Parameters, client_manager: ClientManager) -> List[Tuple[ClientProxy, FitIns]]:
            """Configure the next round of training."""
            log.debug("configure_fit function")
            
            round_id = self.record_new_round(server_round, "FIT")
            client_instructions = super().configure_fit(server_round, parameters, client_manager)
            self.configure_clients_in_round(client_instructions, round_id)

            return client_instructions

        def aggregate_fit(self, server_round: int, results: List[Tuple[ClientProxy, FitRes]],
                          failures: List[Union[Tuple[ClientProxy, FitRes], BaseException]]) -> Tuple[Optional[Parameters], Dict[str, Scalar]]:
            """Aggregate training results."""
            log.debug("aggregate_fit function")
            return super().aggregate_fit(server_round, results, failures)

        def configure_evaluate(self, server_round: int, parameters: Parameters, client_manager: ClientManager) -> List[Tuple[ClientProxy, EvaluateIns]]:
            """Configure the next round of evaluation."""
            log.debug("configure_evaluate function")

            round_id = self.record_new_round(server_round, "EVAL")
            client_instructions = super().configure_fit(server_round, parameters, client_manager)
            self.configure_clients_in_round(client_instructions, round_id)

            return client_instructions

        def aggregate_evaluate(self, server_round: int, results: List[Tuple[ClientProxy, EvaluateRes]], 
                               failures: List[Union[Tuple[ClientProxy, EvaluateRes], BaseException]]) -> Tuple[Optional[float], Dict[str, Scalar]]:
            """Aggregate evaluation results."""
            log.debug("aggregate_evaluate function")
            return super().aggregate_evaluate(server_round, results, failures)
        
        # Not used
        # def initialize_parameters(self, client_manager: ClientManager):
        #     """Initialize the (global) model parameters."""
        #     log.debug("initialize_parameters function")
        #     return super().initialize_parameters(client_manager)
        # def evaluate(self, parameters: Parameters):
        #     """Evaluate the current model parameters."""
        #     log.debug("evaluate function")
        #     return super().evaluate(parameters)

        # ====== End Flower functions ======
    return MonitorFlwrStrategy
