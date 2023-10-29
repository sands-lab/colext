# Copied from https://github.com/adap/flower/blob/main/examples/quickstart-pytorch/server.py
from typing import List, Tuple

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' # Disable tensorflow logging messages
import argparse
import flwr as fl
from flwr.common import Metrics
from fltb.decorators import MonitorFlwrStrategy

# Define metric aggregation function
def weighted_average(metrics: List[Tuple[int, Metrics]]) -> Metrics:
    # Multiply accuracy of each client by number of examples used
    accuracies = [num_examples * m["accuracy"] for num_examples, m in metrics]
    examples = [num_examples for num_examples, _ in metrics]

    # Aggregate and return custom metric (weighted average)
    return {"accuracy": sum(accuracies) / sum(examples)}

# If you define your own class, decorate it with the MonitorFlwrStrategy
# @MonitorFlwrStrategy
# class YourFLStrategy(fl.server.strategy.FedAvg):
#     pass

def get_args():
    parser = argparse.ArgumentParser(
                    prog='FL Server',
                    description='Starts the FL server')
    
    parser.add_argument('-n', '--num_clients', type=int, required=True, help="number of FL clients")
    parser.add_argument('-r', '--num_rounds', type=int, required=True, help="number of FL rounds")
    
    args = parser.parse_args()

    assert args.num_clients > 0, "Number of clients should be larger than 0"

    return args

if __name__ == '__main__':
    args = get_args()

    n_clients = args.num_clients
    n_rounds = args.num_clients
    # Decorate existing Flwr strategy
    # The decoration does nothing if outsite the FLTB environment
    monitored_strategy = MonitorFlwrStrategy(fl.server.strategy.FedAvg)
    strategy = monitored_strategy( 
        min_fit_clients=n_clients, 
        min_evaluate_clients=n_clients, 
        min_available_clients=n_clients, 
        evaluate_metrics_aggregation_fn=weighted_average)

    # Start Flower server
    fl.server.start_server(
        server_address="0.0.0.0:8080",
        config=fl.server.ServerConfig(num_rounds=n_rounds),
        strategy=strategy,
    )

    print("Server stopped.")