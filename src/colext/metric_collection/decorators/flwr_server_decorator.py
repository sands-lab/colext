from datetime import datetime, timezone
import os
import psycopg
from psycopg import sql
from typing import List, Tuple, Union, Optional, Dict
from flwr.common import (FitIns, Parameters, FitRes, Scalar, EvaluateIns, EvaluateRes)
from flwr.server.client_manager import ClientManager
from flwr.server.client_proxy import ClientProxy

from colext.common.logger import log
from colext.common.utils import get_colext_env_var_or_exit

# Class inheritence inside a decorator was inspired by:
# https://stackoverflow.com/a/18938008
def MonitorFlwrStrategy(FlwrStrategy):
    COLEXT_ENV = os.getenv("COLEXT_ENV", "0")
    if not COLEXT_ENV:
        log.debug("Decorator used outside of COLEXT_ENV environment. Not decorating.")
        return FlwrStrategy

    log.debug("Decorating user Flower server class with Monitor class")
    class _MonitorFlwrStrategy(FlwrStrategy):
        def __init__(self, *args, **kwargs):
            log.debug("init function")
            super().__init__(*args, **kwargs)

            self.JOB_ID = get_colext_env_var_or_exit("COLEXT_JOB_ID")
            self.DB_CONNECTION = self.create_db_connection()
            self.clients_cid_to_db_id = {}

            # Temp variable to hold eval round id between fit/evaluate and configure_[fit/evaluate]
            self.current_round_id = None

        def create_db_connection(self):
            # DB parameters are read from env variables
            return psycopg.connect()

        def record_start_round(self, server_round: int, stage: str):
            cursor = self.DB_CONNECTION.cursor()
            query = """
                    INSERT INTO rounds(round_number, start_time, job_id, stage) \
                    VALUES (%s, %s, %s, %s) returning round_id
                """
            data = (str(server_round), datetime.now(timezone.utc), str(self.JOB_ID), stage)
            cursor.execute(query, data)
            round_id = cursor.fetchone()[0]

            query = "INSERT INTO server_round_metrics(round_id) VALUES (%s)"
            data = (round_id,)
            cursor.execute(query, data)

            self.DB_CONNECTION.commit()
            cursor.close()

            return round_id

        def record_end_round(self, server_round: int, round_type: str, dist_accuracy: float = None, srv_accuracy: float = None):
            cursor = self.DB_CONNECTION.cursor()

            dist_accuracy = to_float_or_None(dist_accuracy)
            srv_accuracy = to_float_or_None(srv_accuracy)

            query = """
                    UPDATE rounds
                    SET end_time = %s,
                        dist_accuracy = %s,
                        srv_accuracy = %s
                    WHERE round_number = %s AND job_id = %s AND stage = %s
                """
            data = (datetime.now(timezone.utc),
                    dist_accuracy, srv_accuracy,
                    str(server_round), str(self.JOB_ID), round_type)
            cursor.execute(query, data)
            self.DB_CONNECTION.commit()
            cursor.close()

        def record_server_round_metric(self, metric, value):
            cursor = self.DB_CONNECTION.cursor()

            query = sql.SQL("""
                UPDATE server_round_metrics
                SET {metric} = %s
                WHERE round_id = %s
            """).format(metric=sql.Identifier(metric))

            data = (value,
                    self.current_round_id)
            cursor.execute(query, data)
            self.DB_CONNECTION.commit()
            cursor.close()

        def configure_clients_in_round(self, client_instructions: List[Tuple[ClientProxy, FitIns]]) -> List[Tuple[ClientProxy, FitIns]]:
            # For some reason flwr decided to have all FitIns point to a single dataclass
            # This prevents specifying a different config per client
            # Maybe it's related to the strategy?
            # base_config, base_fit_ins = client_instructions[0]
            # client_instructions = [(c_proxy, copy.deepcopy(fit_ins)) for (c_proxy, fit_ins) in client_instructions]
            # TODO !!! The below solution is inneficient. The more clients we have the mode data we send !!!

            for _, fit_ins in client_instructions:  # First (ClientProxy, FitIns) pair
                fit_ins.config["COLEXT_ROUND_ID"] = self.current_round_id

            return client_instructions

        # ====== Flower functions ======

        def configure_fit(self, server_round: int, parameters: Parameters, client_manager: ClientManager) -> List[Tuple[ClientProxy, FitIns]]:
            """Configure the next round of training."""
            log.debug("configure_fit function")

            self.current_round_id = self.record_start_round(server_round, "FIT")

            self.record_server_round_metric("configure_time_start", datetime.now(timezone.utc))
            client_instructions = super().configure_fit(server_round, parameters, client_manager)
            self.record_server_round_metric("configure_time_end", datetime.now(timezone.utc))

            self.configure_clients_in_round(client_instructions)
            return client_instructions

        def aggregate_fit(self, server_round: int, results: List[Tuple[ClientProxy, FitRes]],
                          failures: List[Union[Tuple[ClientProxy, FitRes], BaseException]]) -> Tuple[Optional[Parameters], Dict[str, Scalar]]:
            """Aggregate training results."""
            log.debug("aggregate_fit function")

            self.record_server_round_metric("aggregate_time_start", datetime.now(timezone.utc))
            aggregate_fit_result = super().aggregate_fit(server_round, results, failures)
            self.record_server_round_metric("aggregate_time_end", datetime.now(timezone.utc))

            self.record_end_round(server_round, "FIT")
            return aggregate_fit_result

        def evaluate(self, server_round: int, parameters: Parameters):
            """Evaluate the current model parameters."""

            self.current_round_id = self.record_start_round(server_round, "EVAL")

            self.record_server_round_metric("eval_time_start", datetime.now(timezone.utc))
            evaluate_result = super().evaluate(server_round, parameters)
            self.record_server_round_metric("eval_time_end", datetime.now(timezone.utc))

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

            self.record_server_round_metric("configure_time_start", datetime.now(timezone.utc))
            client_instructions = super().configure_evaluate(server_round, parameters, client_manager)
            self.record_server_round_metric("configure_time_end", datetime.now(timezone.utc))

            self.configure_clients_in_round(client_instructions)
            if not client_instructions:
                log.debug(f"No client instructions. Evaluation won't happen! {client_instructions=}")

            return client_instructions

        def aggregate_evaluate(self, server_round: int, results: List[Tuple[ClientProxy, EvaluateRes]],
                               failures: List[Union[Tuple[ClientProxy, EvaluateRes], BaseException]]) -> Tuple[Optional[float], Dict[str, Scalar]]:
            """Aggregate evaluation results."""
            log.debug("aggregate_evaluate function")

            self.record_server_round_metric("aggregate_time_start", datetime.now(timezone.utc))
            aggregate_eval_result = super().aggregate_evaluate(server_round, results, failures)
            self.record_server_round_metric("aggregate_time_end", datetime.now(timezone.utc))

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
