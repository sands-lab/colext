import os
import psycopg
from typing import List, Tuple, Union, Optional, Dict
from flwr.common import (FitIns, Parameters, FitRes, Scalar, EvaluateIns, EvaluateRes)
from flwr.server.client_manager import ClientManager
from flwr.server.client_proxy import ClientProxy

from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit

from colext.metric_collection.network_manager import NetworkPubSub
import time
import threading

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
            self.clients_cid_to_db_id = {}

            #publishing
            self.pub_epoch = NetworkPubSub("epoch")
            self.pub_time = NetworkPubSub("time")

            # this is the init time for the client
            self.pub_time.publish(0)


            # Temp variable to hold eval round id between evaluate and configure_evaluate
            self.eval_round_id = None

        

        
        def create_db_connection(self):
            # DB parameters are read from env variables
            return psycopg.connect()

        def record_start_round(self, server_round: int, stage: str):
            cursor = self.DB_CONNECTION.cursor()
            sql = "INSERT INTO rounds(round_number, start_time, job_id, stage) \
                    VALUES (%s, CURRENT_TIMESTAMP, %s, %s) returning round_id"
            data = (str(server_round), str(self.JOB_ID), stage)
            cursor.execute(sql, data)
            round_id = cursor.fetchone()[0]
            self.DB_CONNECTION.commit()
            cursor.close()

            if server_round == 0:
                # publish 1 at the start of round which is the first time iter to be used in client
                self.pub_time.publish(1)

            return round_id

        def record_end_round(self, server_round: int, round_type: str, dist_accuracy: float = None, srv_accuracy: float = None):
            cursor = self.DB_CONNECTION.cursor()

            dist_accuracy = to_float_or_None(dist_accuracy)
            srv_accuracy = to_float_or_None(srv_accuracy)

            sql = """
                    UPDATE rounds
                    SET end_time = CURRENT_TIMESTAMP,
                        dist_accuracy = %s,
                        srv_accuracy = %s
                    WHERE round_number = %s AND job_id = %s AND stage = %s
                """
            data = (dist_accuracy, srv_accuracy, str(server_round), str(self.JOB_ID), round_type)
            cursor.execute(sql, data)
            self.DB_CONNECTION.commit()
            cursor.close()

            #network recording
            self.pub_epoch.publish(server_round)


        def configure_clients_in_round(self, client_instructions: List[Tuple[ClientProxy, FitIns]], round_id: int) -> List[Tuple[ClientProxy, FitIns]]:
            # For some reason flwr decided to have all FitIns point to a single dataclass
            # This prevents specifying a different config per client
            # Maybe it's related to the strategy?
            # base_config, base_fit_ins = client_instructions[0]
            # client_instructions = [(c_proxy, copy.deepcopy(fit_ins)) for (c_proxy, fit_ins) in client_instructions]
            # TODO !!! The below solution is inneficient. The more clients we have the mode data we send !!!

            for _, fit_ins in client_instructions:  # First (ClientProxy, FitIns) pair
                fit_ins.config["COLEXT_ROUND_ID"] = round_id

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

        def evaluate(self, server_round: int, parameters: Parameters):
            """Evaluate the current model parameters."""
            self.eval_round_id = self.record_start_round(server_round, "EVAL")
            evaluate_result = super().evaluate(server_round, parameters)
            log.debug(f"{evaluate_result=}")
            if evaluate_result:
                _, srv_eval_metrics = evaluate_result
            else:
                srv_eval_metrics = {}

            self.record_end_round(server_round, "EVAL", srv_accuracy=srv_eval_metrics.get("accuracy"))
            return evaluate_result

        def configure_evaluate(self, server_round: int, parameters: Parameters, client_manager: ClientManager) -> List[Tuple[ClientProxy, EvaluateIns]]:
            """Configure the next round of evaluation."""
            log.debug("configure_evaluate function")

            client_instructions = super().configure_evaluate(server_round, parameters, client_manager)
            self.configure_clients_in_round(client_instructions, self.eval_round_id)
            if not client_instructions:
                log.debug(f"No client instructions. Evaluation won't happen! {client_instructions=}")

            return client_instructions

        def aggregate_evaluate(self, server_round: int, results: List[Tuple[ClientProxy, EvaluateRes]],
                               failures: List[Union[Tuple[ClientProxy, EvaluateRes], BaseException]]) -> Tuple[Optional[float], Dict[str, Scalar]]:
            """Aggregate evaluation results."""
            log.debug("aggregate_evaluate function")
            aggregate_eval_result = super().aggregate_evaluate(server_round, results, failures)
            _, dist_eval_metrics = aggregate_eval_result
            log.debug(f"{aggregate_eval_result=}")
            self.record_end_round(server_round, "EVAL", dist_accuracy=dist_eval_metrics.get("accuracy"))
            return aggregate_eval_result

        # Not used
        # def initialize_parameters(self, client_manager: ClientManager):
        #     """Initialize the (global) model parameters."""
        #     log.debug("initialize_parameters function")
        #     return super().initialize_parameters(client_manager)

        # ====== End Flower functions ======
    return _MonitorFlwrStrategy


def to_float_or_None(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        if value is not None:
            log.debug(f"Found accuracy metric but could not parse value as float. Value={value}. Ignoring.")
        return None