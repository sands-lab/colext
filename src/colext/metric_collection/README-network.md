# Documentation on how the Network control system works



the guide is divided into 2 main parts: 
- how to setup and use
- how it works
# Setup and usage guide
in order to for the system to work some setup is needed to work
## Setup

everything works in joint with CoLExT directly without setup with the exception of the rabbitMQ broker container.

to setup the rabbitMQ broker we will use the provided files found in in this folder
```
src\colext\exp_deployers\sbc_deployer\microk8s\rabbitmq-broker
```

run the following commands to setup the rabbitMQ broker in the server:

```bash
mk apply -f rabbitmq-broker-configmap.yaml
mk apply -f rabbitmq-broker-deploy.yaml
mk apply -f rabbitmq-broker-service.yaml
```
optionally, to graphiclly control and monitor the broker deploy the managmenet service :
```bash
mk apply -f rabbitmq-broker-mngmt-service.yaml
```
the managment service can be accessed as a website in port 31672




## Guide on config syntax

we first define the network configuration and then apply these configuration to the target clients.

static network defining:
-
```yaml
network:
    - tag: network_name # just a reference name
    upstream: #rules for packets leaving the client
        rule_name: value 
    downstream: #rule for packets incoming to the client
        rule_name: value
```
the tag is the name of the network configuration defined below. this tag is used to assign it to clients later.
when defining a static network, 2 directions can be defined: upstream and downstream. then specific network rules and their values can specified for each network direction.

Note: you can define either or both network directions only

this is the list of network rules that can be defined:
- Speed:
    - rate: bandwidth rate in bits per second - (G/M/K/)bps 

- latency:
    - delay: round trip network delay, valid range - (0ms-60min) decimal is allowed
    - delay-distribution: valid inputs - normal,pareto,paretonormal

- packets:
    - loss: round trip packet loss rate  (%)
    - duplicate: round trip packet duplication rate (%)
    - corrupt: packet corruption rate (%)
    - reordering: packet reordering rate (%)
    - limit: limits the number of packets the qdisc may hold when doing delay

Note: network rules follows tcconfig formatting - (https://tcconfig.readthedocs.io/en/latest/pages/usage/tcset/index.html)

dynamic network defining:
-
dynamic network with defined ruleset:
```yaml
network:
    - tag: network_name:
      dynamic:
      - iterator: iterator # can be either time or epoch
        structure: [banwdith,latency] # a list of network rules to define command structure below
        commands:
        #- [iter value , set/del , direction , bandwidth value , latency value ]
        - [5,   set, outgoing, 100Mbps,  100ms]
        - [10,  set, outgoing, -1,       1ms]
        - [20,  set, outgoing, 1000Mbps, 0.1s]
        - [100, del, outgoing]
```
when defining dynamic networks, include the dynamic key isntead of upstream/downstream.

in dynamic network, 3 things are defined:
- iterator: type of iterator to use (example: time , epoch)
- structure: define a list of networks rules structure the commands below will follow. by default the structure will be [bandwidth,latency] if structure is not defined.
- commands/script: define a set of rules at set iterator time following the structure defined above. 

the commands follow this structure [iterator time, command type, direction , rule values...]
- iterator time: define the time the command is exected depending in the iterator value
- command type: can be either set or del. setting and/or updating new rules and deleting rules in a given direction respectively
- direciton: either incoming or outgoing
- rule values: define the valeus of the rule structure defined.
 

network applying:
-

```yaml
clients:
    - dev_type: JetsonOrinNano
      add_args: "--max_step_count=200"
      network: slow

    - dev_type: OrangePi5B
      add_args: "--max_step_count=100"
      network: 
        - default
        - DynFast
```

when defining the clients in the client section in the CoLExT config file, you can assign the defined networks for each client.

by adding a network parameter and giving either a single network tag or a list of network tags as shown above

Note: make sure that the network tags is synactially correct as defined as it is case-senstive.



# How the system works

The system has 3 main sections. it first reads and validates the colext config file in experiment_dispartcher.py. Then, it translates and deploy those network rules as files to the nodes in sbc_deployer folder. Lastly, the network rules are excuted at the specified time in the network manager.


### experiment_dispatcher.py

- static
    - read static
    - validate static
- dynamic
    - validating structure
    - validating commands

explain overall structure

**static:**
explain how its read and validated

**dynamic:**
explain how its read and validated



### sbc_deployer folder

- rabbitmq-broker
- kubernetes_utils.py
- sub_deployer.py

**rabbitmq broker**
explain what is it and its perpose

**kuberentes functions**
explain the kubernetes functions needed and why

**sbc_deployment**
explain how the cinfg dict and read and applied and deployed


### network_manager.py

- Generator
- PubSub
    - client decorator
    - server decorator

**client decorator**
explain what is done in the client deco

**server decorator**
explain what is done in the server deco

**PubSub**
explain the pubsub and how it interacts with broker and decorators

**generator**
explain how generators is created and used in realation with the sub




System is done by: Abdullah Alamoudi with the guidance of Eng.Amandio and supervision of Prof. Marco Canini


