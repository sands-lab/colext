# Based on: https://github.com/adap/flower/blob/dcffb484fb7d1e712f65d414fb31aa021f0a760e/examples/quickstart-pytorch/server.py
import argparse
from typing import List, Tuple

from flwr.server import ServerApp, ServerConfig
from flwr.server.strategy import FedAvg
from flwr.common import Metrics
from colext import MonitorFlwrStrategy

# Define metric aggregation function
def weighted_average(metrics: List[Tuple[int, Metrics]]) -> Metrics:
    # Multiply accuracy of each client by number of examples used
    accuracies = [num_examples * m["accuracy"] for num_examples, m in metrics]
    examples = [num_examples for num_examples, _ in metrics]

    # Aggregate and return custom metric (weighted average)
    return {"accuracy": sum(accuracies) / sum(examples)}


@MonitorFlwrStrategy
class FlowerStrategy(FedAvg):
    pass

# Define config
config = ServerConfig(num_rounds=3)


# Flower ServerApp
# app = ServerApp(
#     config=config,
#     strategy=strategy,
# )

def get_args():
    parser = argparse.ArgumentParser(
                    prog='FL Server',
                    description='Starts the FL server')

    parser.add_argument('-n', '--num_clients', type=int, required=True, help="number of FL clients")
    parser.add_argument('-r', '--num_rounds', type=int, required=True, help="number of FL rounds")

    args = parser.parse_args()

    assert args.num_clients > 0, "Number of clients should be larger than 0"
    assert args.num_rounds > 0, "Number of rounds should be larger than 0"

    return args

# Legacy mode
if __name__ == "__main__":
    from flwr.server import start_server

    args = get_args()

    n_clients = args.num_clients
    n_rounds = args.num_rounds

    strategy = FlowerStrategy(
        min_fit_clients=n_clients,
        min_evaluate_clients=n_clients,
        min_available_clients=n_clients,
        evaluate_metrics_aggregation_fn=weighted_average)


    start_server(
        server_address="0.0.0.0:8080",
        config=ServerConfig(num_rounds=n_rounds),
        strategy=strategy,
    )