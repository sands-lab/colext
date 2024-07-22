import os
import argparse
import time
import flwr as fl
from colext import MonitorFlwrClient

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' # Disable tensorflow logging messages

# Define Flower client
# The decoration does nothing if outsite the CoLExT environment
@MonitorFlwrClient
class FlowerClient(fl.client.NumPyClient):
    def __init__(self, measurement_duration) -> None:
        super().__init__()
        self.measurement_duration = measurement_duration

    def get_parameters(self, config):
        return []

    def fit(self, parameters, config):
        time.sleep(self.measurement_duration)
        return self.get_parameters(config={}), 0, {}

    def evaluate(self, parameters, config):
        return 0.0, 1, {"accuracy": 0}

def get_args():
    parser = argparse.ArgumentParser(
                    prog='FL Client',
                    description='Starts the FL client')

    parser.add_argument('--flserver_address', type=str, default="127.0.0.1:8080", help="FL server address ip:port")
    parser.add_argument('--measurement_duration', type=int, help="Time for measurement in seconds")
    return parser.parse_args()

if __name__ == '__main__':
    args = get_args()

    flserver_address = args.flserver_address
    measurement_duration = args.measurement_duration

    # Start Flower client
    fl.client.start_numpy_client(
        server_address=flserver_address,
        client=FlowerClient(measurement_duration),
    )

    print("Numpy client finished")
