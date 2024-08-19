"""Start a Flower server.
Derived from Flower Android example."""
import subprocess

from flwr.server import ServerConfig, start_server
from flwr.server.client_manager import ClientManager

from local_strategies.fedavg import FedAvg
from local_strategies.fedadagrad import FedAdagrad
from local_strategies.fedadam import FedAdam
from local_strategies.fedyogi import FedYogi

import psycopg2

import re

from typing import List, Tuple, Union, Optional, Dict, Callable
from flwr.common import (
    FitIns,
    Parameters, FitRes, Scalar, EvaluateIns, EvaluateRes, NDArrays,
)
from flwr.server.client_proxy import ClientProxy


class CustomClientConfigStrategy(FedAvg):
    JOB_ID: int
    FIT_ROUND_ID: int
    EVAL_ROUND_ID: int
    CLIENTS: Dict

    def __init__(
            self,
            *,
            fraction_fit: float = 1.0,
            fraction_evaluate: float = 1.0,
            min_fit_clients: int = 1,
            min_evaluate_clients: int = 1,
            min_available_clients: int = 1,
            evaluate_fn: Optional[
                Callable[
                    [int, NDArrays, Dict[str, Scalar]],
                    Optional[Tuple[float, Dict[str, Scalar]]],
                ]
            ] = None,
            on_fit_config_fn: Optional[Callable[[int], Dict[str, Scalar]]] = None,
            on_evaluate_config_fn: Optional[Callable[[int], Dict[str, Scalar]]] = None,
            accept_failures: bool = True,
            initial_parameters: Optional[Parameters] = None,
            db_conn,
            job_id: int,
            clients: Dict
    ) -> None:
        super().__init__(fraction_fit=fraction_fit,
                         fraction_evaluate=fraction_evaluate,
                         min_fit_clients=min_fit_clients,
                         min_evaluate_clients=min_evaluate_clients,
                         min_available_clients=min_available_clients,
                         evaluate_fn=evaluate_fn,
                         on_fit_config_fn=on_fit_config_fn,
                         on_evaluate_config_fn=on_evaluate_config_fn,
                         accept_failures=accept_failures,
                         initial_parameters=initial_parameters)
        self.DB_CONNECTION = db_conn
        self.JOB_ID = job_id
        self.CLIENTS = clients

    def configure_fit(
            self, server_round: int, parameters: Parameters, client_manager: ClientManager
    ) -> List[Tuple[ClientProxy, FitIns]]:

        client_instructions = super().configure_fit(server_round, parameters, client_manager)

        cursor = self.DB_CONNECTION.cursor()

        sql = "INSERT INTO fl_testbed_logging.rounds(round_number, start_time, job_id, fit_eval) VALUES (%s, CURRENT_TIMESTAMP, %s, %s) returning round_id"
        data = (str(server_round), str(self.JOB_ID), "FIT")
        cursor.execute(sql, data)
        self.FIT_ROUND_ID = cursor.fetchone()[0]

        sql = "INSERT INTO fl_testbed_logging.clients_in_rounds (client_id, round_id, client_state) values (%s, %s, %s) returning cir_id"
        for (proxy, fit_ins) in client_instructions:  # First (ClientProxy, FitIns) pair
            ip_address = re.search(r'ipv4:(\d+\.\d+\.\d+\.\d+):\d+', proxy.cid.__str__()).group(1) if re.search(
                r'ipv4:(\d+\.\d+\.\d+\.\d+):\d+', proxy.cid.__str__()) else None
            cur_client_state = "OFFLINE"
            if check_android_device_online(ip_address):
                cur_client_state = "AVAILABLE"
            data = (str(self.CLIENTS[ip_address]), str(self.FIT_ROUND_ID), cur_client_state)
            cursor.execute(sql, data)
            result = cursor.fetchone()[0]
            fit_ins.config["CIR_ID"] = result

        self.DB_CONNECTION.commit()
        cursor.close()

        return client_instructions

    def aggregate_fit(self, server_round: int, results: List[Tuple[ClientProxy, FitRes]],
                      failures: List[Union[Tuple[ClientProxy, FitRes], BaseException]]) -> Tuple[
        Optional[Parameters], Dict[str, Scalar]]:

        client_results = super().aggregate_fit(server_round, results, failures)

        cursor = self.DB_CONNECTION.cursor()

        sql = "UPDATE fl_testbed_logging.rounds SET end_time = CURRENT_TIMESTAMP WHERE round_id = %s"
        data = (self.FIT_ROUND_ID,)

        cursor.execute(sql, data)
        self.DB_CONNECTION.commit()
        cursor.close()

        return client_results

    def configure_evaluate(self, server_round: int, parameters: Parameters, client_manager: ClientManager) -> List[
        Tuple[ClientProxy, EvaluateIns]]:

        client_instructions = super().configure_evaluate(server_round, parameters, client_manager)

        cursor = self.DB_CONNECTION.cursor()

        sql = "INSERT INTO fl_testbed_logging.rounds(round_number, start_time, job_id, fit_eval) VALUES (%s, CURRENT_TIMESTAMP, %s, %s) returning round_id"
        data = (str(server_round), str(self.JOB_ID), "EVAL")
        cursor.execute(sql, data)
        self.EVAL_ROUND_ID = cursor.fetchone()[0]

        sql = "INSERT INTO fl_testbed_logging.clients_in_rounds (client_id, round_id, client_state) values (%s, %s, %s) returning cir_id"
        for (proxy, fit_ins) in client_instructions:  # First (ClientProxy, FitIns) pair
            ip_address = re.search(r'ipv4:(\d+\.\d+\.\d+\.\d+):\d+', proxy.cid.__str__()).group(1) if re.search(
                r'ipv4:(\d+\.\d+\.\d+\.\d+):\d+', proxy.cid.__str__()) else None
            data = (str(self.CLIENTS[ip_address]), str(self.EVAL_ROUND_ID), "AVAILABLE")
            cursor.execute(sql, data)
            result = cursor.fetchone()[0]
            fit_ins.config["CIR_ID"] = result

        self.DB_CONNECTION.commit()
        cursor.close()

        return client_instructions

    def aggregate_evaluate(self, server_round: int, results: List[Tuple[ClientProxy, EvaluateRes]],
                           failures: List[Union[Tuple[ClientProxy, EvaluateRes], BaseException]]) -> Tuple[
        Optional[float], Dict[str, Scalar]]:

        client_results = super().aggregate_evaluate(server_round, results, failures)

        cursor = self.DB_CONNECTION.cursor()

        sql = "UPDATE fl_testbed_logging.rounds SET end_time = CURRENT_TIMESTAMP, accuracy = %s WHERE round_id = %s"
        data = (client_results[0], self.EVAL_ROUND_ID)

        cursor.execute(sql, data)
        self.DB_CONNECTION.commit()
        cursor.close()

        return client_results


def fit_config(server_round: int):
    """Return training configuration dict for each round.

    Keep batch size fixed at 32, perform two rounds of training with one
    local epoch, increase to two local epochs afterwards.
    """
    config = {
        "batch_size": 32,
        "local_epochs": 5,
    }
    return config


def run_server(db_conn, job_id, clients, server_ip, server_port):
    strategy = CustomClientConfigStrategy(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=1,
        min_evaluate_clients=1,
        min_available_clients=1,
        evaluate_fn=None,
        on_fit_config_fn=fit_config,
        db_conn=db_conn,
        job_id=job_id,
        clients=clients,
    )

    try:

        start_server(
            server_address=f"{server_ip}:{server_port}",
            config=ServerConfig(num_rounds=10),
            strategy=strategy,
        )

    except KeyboardInterrupt:
        return


def check_android_device_online(device_ip):
    # result = subprocess.run(['adb', 'devices'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    #                        check=True)
    # result_grep = subprocess.run(['grep', device_ip], input=result.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    result_grep = subprocess.run('adb devices | grep ' + device_ip,
                                 check=True,
                                 capture_output=True,
                                 shell=True,
                                 text=True)
    return result_grep.returncode == 0 and 'device' in result_grep.stdout
