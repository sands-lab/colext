# Copied from: https://github.com/adap/flower/blob/dcffb484fb7d1e712f65d414fb31aa021f0a760e/examples/quickstart-pytorch/client.py
import os
import argparse
import warnings
from collections import OrderedDict

from flwr.client import NumPyClient, ClientApp
from flwr_datasets import FederatedDataset
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision.transforms import Compose, Normalize, ToTensor
from tqdm import tqdm

from colext import MonitorFlwrClient

# #############################################################################
# 1. Regular PyTorch pipeline: nn.Module, train, test, and DataLoader
# #############################################################################

warnings.filterwarnings("ignore", category=UserWarning)
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

class Net(nn.Module):
    """Model (simple CNN adapted from 'PyTorch: A 60 Minute Blitz')"""

    def __init__(self) -> None:
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(-1, 16 * 5 * 5)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)


def train(net, trainloader, epochs):
    """Train the model on the training set."""
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(net.parameters(), lr=0.001, momentum=0.9)
    for _ in range(epochs):
        step = 0

        for batch in tqdm(trainloader, "Training"):
            images = batch["img"]
            labels = batch["label"]
            optimizer.zero_grad()
            criterion(net(images.to(DEVICE)), labels.to(DEVICE)).backward()
            optimizer.step()

            if step >= max_step_count:
                break
            else:
                step += 1


def test(net, testloader):
    """Validate the model on the test set."""
    criterion = torch.nn.CrossEntropyLoss()
    correct, loss = 0, 0.0
    with torch.no_grad():
        step = 0

        for batch in tqdm(testloader, "Testing"):
            images = batch["img"].to(DEVICE)
            labels = batch["label"].to(DEVICE)
            outputs = net(images)
            loss += criterion(outputs, labels).item()
            correct += (torch.max(outputs.data, 1)[1] == labels).sum().item()

            if step >= max_step_count:
                break
            else:
                step += 1
    accuracy = correct / len(testloader.dataset)
    return loss, accuracy


def load_data(partition_id):
    """Load partition CIFAR10 data."""
    n_partitions = int(os.getenv("COLEXT_N_CLIENTS"))
    fds = FederatedDataset(dataset="cifar10", partitioners={"train": n_partitions})
    partition = fds.load_partition(partition_id)
    # Divide data on each node: 80% train, 20% test
    partition_train_test = partition.train_test_split(test_size=0.2)
    pytorch_transforms = Compose(
        [ToTensor(), Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))]
    )

    def apply_transforms(batch):
        """Apply transforms to the partition from FederatedDataset."""
        batch["img"] = [pytorch_transforms(img) for img in batch["img"]]
        return batch

    partition_train_test = partition_train_test.with_transform(apply_transforms)
    trainloader = DataLoader(partition_train_test["train"], batch_size=32, shuffle=True)
    testloader = DataLoader(partition_train_test["test"], batch_size=32)

    return trainloader, testloader


# #############################################################################
# 2. Federation of the pipeline with Flower
# #############################################################################

# Get partition id
# parser = argparse.ArgumentParser(description="Flower")
# parser.add_argument(
#     "--partition-id",
#     choices=[0, 1, 2],
#     default=0,
#     type=int,
#     help="Partition of the dataset divided into 3 iid partitions created artificially.",
# )
partition_id = int(os.getenv("COLEXT_CLIENT_ID"))

# Load model and data (simple CNN, CIFAR-10)
net = Net().to(DEVICE)
trainloader, testloader = load_data(partition_id=partition_id)

# Define Flower client
# The decoration does nothing if outsite the CoLExT environment
@MonitorFlwrClient
class FlowerClient(NumPyClient):
    def get_parameters(self, config):
        return [val.cpu().numpy() for _, val in net.state_dict().items()]

    def set_parameters(self, parameters):
        params_dict = zip(net.state_dict().keys(), parameters)
        state_dict = OrderedDict({k: torch.tensor(v) for k, v in params_dict})
        net.load_state_dict(state_dict, strict=True)

    def fit(self, parameters, config):
        self.set_parameters(parameters)
        train(net, trainloader, epochs=1)
        return self.get_parameters(config={}), len(trainloader.dataset), {}

    def evaluate(self, parameters, config):
        self.set_parameters(parameters)
        loss, accuracy = test(net, testloader)
        return loss, len(testloader.dataset), {"accuracy": accuracy}


def client_fn(cid: str):
    """Create and return an instance of Flower `Client`."""
    return FlowerClient().to_client()


# Flower ClientApp
app = ClientApp(
    client_fn=client_fn,
)

def get_args():
    parser = argparse.ArgumentParser(
                    prog='FL Client',
                    description='Starts the FL client')

    parser.add_argument('--flserver_address', type=str, default="127.0.0.1:8080", help="FL server address ip:port")
    parser.add_argument('--max_step_count', default=1000, type=int, help="Configure number of steps for train and test")
    args = parser.parse_args()
    return args

# Legacy mode
if __name__ == "__main__":
    from flwr.client import start_client

    args = get_args()

    flserver_address = args.flserver_address
    max_step_count = args.max_step_count

    start_client(
        server_address=flserver_address,
        client=FlowerClient().to_client(),
    )