# Copied from: https://github.com/adap/flower/blob/main/examples/quickstart-pytorch/client.py
import warnings
from collections import OrderedDict
import argparse

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' # Disable tensorflow logging messages
import flwr as fl
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision.datasets import CIFAR10
from torchvision.transforms import Compose, Normalize, ToTensor
from tqdm import tqdm
from colext import MonitorFlwrClient

# #############################################################################
# 1. Regular PyTorch pipeline: nn.Module, train, test, and DataLoader
# #############################################################################

warnings.filterwarnings("ignore", category=UserWarning)
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
tiny_rounds = False
print(f"Using device = {DEVICE}")

# MODEL_CONFIG = [3, 20, 20, 64, 64, 64, 64, 10]
# MODEL_CONFIG = [3, 48, 48, 96, 96, 96, 96, 10]
MODEL_CONFIG = [3, 96, 96, 192, 192, 192, 192, 10]
class Net(nn.Module):
    # def __init__(self) -> None:
    #     super().__init__()
    #     self.conv1_1 = nn.Conv2d(MODEL_CONFIG[0], MODEL_CONFIG[1], 3, padding=1)
    #     self.conv1_2 = nn.Conv2d(MODEL_CONFIG[1], MODEL_CONFIG[2], 3, padding=1)
    #     self.max_pool = nn.MaxPool2d(3, stride=2, padding=1)
    #     self.conv2_1 = nn.Conv2d(MODEL_CONFIG[2], MODEL_CONFIG[3], 3, padding=1)
    #     self.conv2_2 = nn.Conv2d(MODEL_CONFIG[3], MODEL_CONFIG[4], 3, padding=1)
    #     self.conv3 = nn.Conv2d(MODEL_CONFIG[4], MODEL_CONFIG[5], 3, padding=1)
    #     self.conv4 = nn.Conv2d(MODEL_CONFIG[5], MODEL_CONFIG[6], 3)
    #     self.conv5 = nn.Conv2d(MODEL_CONFIG[6], MODEL_CONFIG[7], 1)
    #     self.relu = nn.ReLU(inplace=True)
    #     self.global_pooling = nn.AvgPool2d(6)
    #     self.flatten = nn.Flatten(start_dim=1)

    # def forward(self, x):
    #     x = self.relu(self.conv1_1(x))
    #     x = self.relu(self.conv1_2(x))
    #     x = self.max_pool(x)

    #     x = self.relu(self.conv2_1(x))
    #     x = self.relu(self.conv2_2(x))
    #     x = self.max_pool(x)

    #     x = self.relu(self.conv3(x))

    #     x = self.relu(self.conv4(x))

    #     x = self.relu(self.conv5(x))
    #     x = self.global_pooling(x)
    #     x = self.flatten(x)
    #     return x

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
        for images, labels in tqdm(trainloader):
        # for images, labels in trainloader:
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
        # for images, labels in tqdm(testloader):
        for images, labels in testloader:
            outputs = net(images.to(DEVICE))
            labels = labels.to(DEVICE)
            loss += criterion(outputs, labels).item()
            correct += (torch.max(outputs.data, 1)[1] == labels).sum().item()

            if step >= max_step_count:
                break
            else:
                step += 1

    accuracy = correct / len(testloader.dataset)
    return loss, accuracy


def load_data():
    """Load CIFAR-10 (training and test set)."""
    trf = Compose([ToTensor(), Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    datapath = os.getenv("COLEXT_PYTORCH_DATASETS", "./data")
    trainset = CIFAR10(datapath, train=True, download=True, transform=trf)
    testset = CIFAR10(datapath, train=False, download=True, transform=trf)
    return DataLoader(trainset, batch_size=32, shuffle=True, pin_memory=True), DataLoader(testset)


# #############################################################################
# 2. Federation of the pipeline with Flower
# #############################################################################

# Load model and data (simple CNN, CIFAR-10)
net = Net().to(DEVICE)
trainloader, testloader = load_data()

# Define Flower client
# The decoration does nothing if outsite the CoLExT environment
@MonitorFlwrClient
class FlowerClient(fl.client.NumPyClient):
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

def get_args():
    parser = argparse.ArgumentParser(
                    prog='FL Client',
                    description='Starts the FL client')

    parser.add_argument('--flserver_address', type=str, default="127.0.0.1:8080", help="FL server address ip:port")
    parser.add_argument('--max_step_count', default=3000, type=int, help="Configure number of steps for train and test")
    args = parser.parse_args()

    return args

if __name__ == '__main__':
    args = get_args()

    flserver_address = args.flserver_address
    max_step_count = args.max_step_count

    # Start Flower client
    fl.client.start_numpy_client(
        server_address=flserver_address,
        client=FlowerClient(),
    )

    print("Numpy client finished")
