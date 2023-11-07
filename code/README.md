This example is similar to the Flower Android Example in Java: https://github.com/adap/flower/tree/main/examples/android-kotlin

Download the training and testing data from https://www.dropbox.com/s/coeixr4kh8ljw6o/cifar10.zip?dl=1 and extract them to cifar10_example/data.

# Original readme: 
# Flower Android Client Example with Kotlin and TensorFlow Lite 2022

> This example demonstrates a federated learning setup with Android Clients. The training on Android is done on a CIFAR10 dataset using TensorFlow Lite. The setup is as follows:
>
> - The CIFAR10 dataset is randomly split across 10 clients. Each Android client holds a local dataset of 5000 training examples and 1000 test examples.
> - The FL server runs in Python but all the clients run on Android.
> - We use a strategy called FedAvgAndroid for this example.
> - The strategy is vanilla FedAvg with a custom serialization and deserialization to handle the Bytebuffers sent from Android clients to Python server.

## Run the demo

Start the Flower server at `./`:

```sh
python3 server.py
```

<details>
<summary>Or without the "3" on windows.</summary>

```sh
python server.py
```

</details>

Install the app on *physical* Android devices and launch it.

<!-- TODO: APK. -->

*Note*: the highest tested JDK version the app supports is 16; it fails to build using JDK 19 on macOS.

In the user interface, fill in:

- Device number: a unique number among 1 ~ 10.
  This number is used to choose the partition of the training dataset.
- Server IP: an IPv4 address of the computer your backend server is running on. You can probably find it in your system network settings.
- Server port: 8080.

Push the first button and load the dataset. This may take a minute.

Push the second button and start the training.
