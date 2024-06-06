import os
import re
import psycopg
from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit

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
    class _MonitorFlwrStrategy(FlwrStrategy):
        def __init__(self, *args, **kwargs):
            log.debug("init function")
            super().__init__(*args, **kwargs)

            self.JOB_ID = get_colext_env_var_or_exit("COLEXT_JOB_ID")
            self.DB_CONNECTION = self.create_db_connection()
            self.clients_ip_to_id = {}

        def create_db_connection(self):
            DB_CONNECTION_INFO = "host=10.0.0.100 dbname=fl_testbed_db_copy user=faustiar_test_user password=faustiar_test_user"
            return psycopg.connect(DB_CONNECTION_INFO)

        def record_start_round(self, server_round: int, stage: str):
            cursor = self.DB_CONNECTION.cursor()
            sql = "INSERT INTO rounds(round_number, start_time, job_id, stage) \
                    VALUES (%s, CURRENT_TIMESTAMP, %s, %s) returning round_id"
            data = (str(server_round), str(self.JOB_ID), stage)
            cursor.execute(sql, data)
            round_id = cursor.fetchone()[0]
            self.DB_CONNECTION.commit()
            cursor.close()

            return round_id

        def record_end_round(self, server_round: int, round_type: str, accuracy: float = None):
            cursor = self.DB_CONNECTION.cursor()

            sql = """
                    UPDATE rounds
                    SET end_time = CURRENT_TIMESTAMP,
                        accuracy = %s
                    WHERE round_number = %s AND job_id = %s AND stage = %s
                """
            data = (accuracy, str(server_round), str(self.JOB_ID), round_type)
            cursor.execute(sql, data)
            self.DB_CONNECTION.commit()
            cursor.close()

        def get_client_db_id(self, client_proxy: ClientProxy) -> int:
            log.info(f"Getting DB ID for client_proxy with cid = {client_proxy.cid}")

            ip_address = re.search(r'ipv4:(\d+\.\d+\.\d+\.\d+:\d+)', client_proxy.cid).group(1)
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

            # For some reason flwr decided to have all FitIns point to a single dataclass
            # This prevents specifying a different config per client
            # Maybe it's related to the strategy?
            # base_config, base_fit_ins = client_instructions[0]
            # client_instructions = [(c_proxy, copy.deepcopy(fit_ins)) for (c_proxy, fit_ins) in client_instructions]
            # TODO !!! The below solution is inneficient. The more clients we have the mode data we send !!!

            # Register clients in round
            sql = """
                    INSERT INTO clients_in_round (client_id, round_id, client_state)
                    VALUES (%s, %s, %s) RETURNING cir_id
                """
            for proxy, fit_ins in client_instructions:  # First (ClientProxy, FitIns) pair
                client_db_id = self.get_client_db_id(proxy)

                cur_client_state = "AVAILABLE"
                data = (client_db_id, str(round_id), cur_client_state)
                cursor.execute(sql, data)
                cir_id = cursor.fetchone()[0]
                # Flower does not support dict in the config ?
                fit_ins.config[f"COLEXT_CIR_MAP_{client_db_id}"] = cir_id

            self.DB_CONNECTION.commit()
            cursor.close()

            return client_instructions

        # ====== Flower functions ======

        def configure_fit(self, server_round: int, parameters: Parameters, client_manager: ClientManager) -> List[Tuple[ClientProxy, FitIns]]:
            """Configure the next round of training."""
            log.debug("configure_fit function")

            client_instructions = super().configure_fit(server_round, parameters, client_manager)
            round_id = self.record_start_round(server_round, "FIT")
            self.configure_clients_in_round(client_instructions, round_id)

            return client_instructions

        def aggregate_fit(self, server_round: int, results: List[Tuple[ClientProxy, FitRes]],
                          failures: List[Union[Tuple[ClientProxy, FitRes], BaseException]]) -> Tuple[Optional[Parameters], Dict[str, Scalar]]:
            """Aggregate training results."""
            log.debug("aggregate_fit function")
            aggregate_fit_result = super().aggregate_fit(server_round, results, failures)
            self.record_end_round(server_round, "FIT")
            return aggregate_fit_result

        def configure_evaluate(self, server_round: int, parameters: Parameters, client_manager: ClientManager) -> List[Tuple[ClientProxy, EvaluateIns]]:
            """Configure the next round of evaluation."""
            log.debug("configure_evaluate function")

            client_instructions = super().configure_evaluate(server_round, parameters, client_manager)
            if client_instructions:
                round_id = self.record_start_round(server_round, "EVAL")
                self.configure_clients_in_round(client_instructions, round_id)
            else:
                log.debug(f"No client instructions. Evaluation won't happen! {client_instructions=}")

            return client_instructions

        def aggregate_evaluate(self, server_round: int, results: List[Tuple[ClientProxy, EvaluateRes]],
                               failures: List[Union[Tuple[ClientProxy, EvaluateRes], BaseException]]) -> Tuple[Optional[float], Dict[str, Scalar]]:
            """Aggregate evaluation results."""
            log.debug("aggregate_evaluate function")
            aggregate_eval_result = super().aggregate_evaluate(server_round, results, failures)
            _, metrics = aggregate_eval_result
            log.debug(f"{aggregate_eval_result=}")
            self.record_end_round(server_round, "EVAL", metrics.get("accuracy"))
            return aggregate_eval_result

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
    return _MonitorFlwrStrategy
