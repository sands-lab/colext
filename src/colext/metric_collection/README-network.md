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

Dynamic network defining:
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
 

Applying network to nodes:
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


## experiment_dispatcher.py

- static
    - read static
    - validate static
- dynamic
    - validating structure
    - validating commands


before processing the network, it checked if its either static or dynamic in the read_network() function before calling the suitable function.

**static:**
for static networks, its processing is divided into 2 seperate functions. Read_static() will accept a dict of the static network. it checks for each direciton if its a string (simplified input) or a dictonary (complete input) and convert each direction into a single network rule to be applied.

the resultant network rule commands is then passed to the validate_static_commands() function to validate the command using the deinfe constant mapping defined like COMMAND_MAPPING and VALIDATION_MAPPING for the rule and its value respectively. then it will output either correctly formatted command or give an error for invalid inputs.


**dynamic:**
for dynamic network, its processing are all packed into a single function with 2 helper functions. the main functions , named read_validate_dynamic(), will accept a dict of the dynamic network and loop through all the key value pairs in the dynamic section. 
it checks for 3 main sections:

- iterator: check it's from the VALID_ITERS constant
- structure: validates this structure is valid by validating each rule name in the structure using the helper function check_rules()
- commands/script: if it's a script then pass the script path. else then parse the commands given the structure similar to the static rule parsing but instead save it as a dict.



## sbc_deployer folder

- rabbitmq-broker
- kubernetes_utils.py
- sbc_deployer.py


**rabbitmq broker**
for the publish subscribe to work. we need a broker to receive and send msgs between the publishers and subscribers. rabbitmq broker folder has all the files needed to start a broker with the specified used ports and service name.

**kuberentes functions**
2 main functions in kubernetes utils is used to create and delete configmaps respectively.

**sbc_deployment**
in deployment, prepare_clients_for_launch functions includes 2 network functions to finalize and generate the files to be send via configmaps. the generate_network_configmap_folder is called with an input of the dict of a clientgroup and their groupid (group id is created right before this function is called at the end). this function will generate files for each assigned network in the clientgroup both static and dynamic. static networks are merged before converted to a file using the merge_static_network_rules() function.

note: groupid is created and saved as a key entry for each clientgroup. it is used to define the name of the files and its location locally before converted to a configmap.

after files for each clientgroup is create it is then converted to a configmap using create_config_map_from_dict() function from kubernetes_utils with its clientgroup id its specified to.

## network_manager.py


### we have 3 classes:

- network generator: a class to hold all functions needed with geenrators
- network manager: main class managing all generators and subscribers
- pubsub: wrapper class for pika (python package for rabbitmq) publish subscribe functions





### publisher/server side

in the server decorator, it will create a PubSub object for each iteration and publish accordingly.
both time and epoch publishers publishes 0 at the init function of the decorator.

Note: publishers for an iter is hardcoded as each publisher will need a unique loop mechnaism and thus making it sufficient.

time publishers will publish only once at time=1 at the start of the first round

epoch publisher will publish at the start of each round in the record_start_round() function.


### subscriber/client side

client decorator will create a networkmanager object and call 2 functions: ParseStaticRules and ParseDynamicRules. 

Note: all files sent via configmaps will resort in the Networks folder in the node.

**Static Rules:**

ParseStaticRules will accept a file (should be .txt file) and parse it executing every line using a subprocess.


**Dynamic Rules:**

When NetworkManager is created it automatically fetchs all the files from the Networks folder and convert all files ending with json or py (dynamic rules and dynamic script respectivly) into generators and make them store them a dictionary with iters as keys and a list of generators as value.

Note: the iterators defined is not hardcoded and fully dependant on the file names as the start of the file name is the iter type for example: time_DynFast_... 

ParseDynamicRules loops the dictionary keys (basicly all available iterators) and make a subscriber for each and then pass a custom Callback function generated using create_callback_for_type function.

create_callback_for_type function returns an anonymous callback function that wraps the CreateCallback function (which is a callback function with generators and iter passed as parameters).

the callback function is called everytime the subscriber gets a value and loops through the generators in efficiently using a state dict to save future results we got when generating previously.

time_loop is called when we get time=1 which loops through the generator for time iter each second with the same manner.

Note: since time is only published twice (time=0,1) the time_loop will be called at time=1 making it called only once.


Dynamic Rules are applied in a similar way to how static rules are applied using Subprocesses.


# missing features and odd bugs

### bugs to be fixed

dynamic network seem to not be able to have around more than 20 commands staticly typed. having more than 20 prevents from executing the commands in the node for some reason

having only dynamic network and not include a static network seems to not work and prevent dynamic rules executing.


### missing features:

scripts for dynamic network: not fully implemented yet, but the system is ready and only just missing the conversion of scripts to generators to work.






System is done by: Abdullah Alamoudi with the guidance of Eng.Amandio and supervision of Prof. Marco Canini


