import os
import argparse
import flwr as fl
from colext import MonitorFlwrStrategy
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' # Disable tensorflow logging messages

# Decorate existing Flwr strategy
# The decoration does nothing if outsite the CoLExT environment
@MonitorFlwrStrategy
class FlowerStrategy(fl.server.strategy.FedAvg):
    pass

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

if __name__ == '__main__':
    args = get_args()

    n_clients = args.num_clients
    n_rounds = args.num_rounds

    strategy = FlowerStrategy(
        min_fit_clients=n_clients,
        min_evaluate_clients=n_clients,
        min_available_clients=n_clients)

    # Start Flower server
    fl.server.start_server(
        server_address="0.0.0.0:8080",
        config=fl.server.ServerConfig(num_rounds=n_rounds),
        strategy=strategy,
    )

    print("Server stopped.")
