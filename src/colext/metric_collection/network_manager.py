# TODO:
'''
1- make a class for pub sub
2- make a class for the rules and make it have a generator for the commands
3- the second class should accept either script or json file as input


'''

import pika
import json
import os
from colext.common.logger import log
import subprocess


class NetworkGenerator:


    def __init__(self,file):
        '''
        accept type (script or json) and file (path to the file)
        and create the generator based on the type
        '''
        self.generator = None
        
        self.file = file
        self.rules = None
        self.struct = None
        self.script = True
        #determine types by splitting the file name
        filesplit = file.split("_")
        if filesplit[-1].endswith(".json"):
            self.filetype = "json"
        elif filesplit[-1].endswith(".py"):
            self.filetype = "script"
        
        #this is the iter type regardless of the file type
        self.type = filesplit[0]
        

        
        if self.filetype == "json":
            self.json_parser()
            self.generator = self.MakeGenerator()
        elif self.filetype == "script":
            self.generator = self.MakeGenerator()
  
    def json_parser(self):
        '''
        given an input json file, parse it and create a dictionary of rules
        '''
        jsondict = json.load(open(self.file, 'r'))
        self.rules = jsondict['commands_dict']
        self.struct = jsondict['structure']
        self.script = False
        #convert all the rules to a command line string
        rules = {}
        for iter in self.rules:
            rules[iter] = []
            for rule in self.rules[iter]:
                rules[iter].append(self.converter(rule, self.struct))
        
        self.rules = rules


    def converter(self,rule, struct):
        '''
        given an input rule and struct convert it to a command line string
        '''
        output = ""
    
        if rule[0] == "del":
            output += "tcdel eth0"
            output += " --direction " + rule[1]
            return output
        elif rule[0] == "set":
            output += "tcset eth0"
        

        for i in range(len(rule)-1):
            if i == 0:
                output += " --direction " + rule[i+1]
            elif rule[i+1] == -1:
                continue
            else:
                output += " --" + struct[i-1] + " " + rule[i+1]
        return output
    def MakeGenerator(self):
        '''
        given an input type and dict
        if type normal, make a generator for the input list of rules
        if type is script, wrap the script with a generator and call the init function
        and return the generator object
        '''
        if self.script:
            self.generator = self.ScriptGenerator()
        else:
            self.generator = self.JsonGenerator()


    def JsonGenerator(self):
        '''
        given an input json file, parse it and create a generator object
        '''
        rules = self.rules
        for key in rules:
            yield key, rules[key]


    def ScriptGenerator(self):
        '''
        given an input script file, parse it and create a generator object
        '''
        pass
    

def JsonCallback(ch, method, properties, body):
    
    pass
def ScriptCallback(ch, method, properties, body):
    
    pass

    

class NetworkManager:


    def __init__(self,folder_path="network/"):
        '''
        parse the static rules and dynamic rules and create the generators

        '''
        self.generators = {}
        self.generatorstype = {"epoch": [],
                                "time": []}
        
        self.Subscribers = {}

        #get all the files in the folder
        files = os.listdir(folder_path)
        #filter the files to get only the json and script files
        files = [f for f in files if f.endswith(".json") or f.endswith(".py")]
        #create the generators for each file
        for file in files:
            self.generators[file] = NetworkGenerator(file)
            #get the type of the generator and add it to the list of generators
            if self.generators[file].type in self.generatorstype:
                self.generatorstype[self.generators[file].type].append(self.generators[file])
            else:
                # assume that iter type verification is done
                self.generatorstype[self.generators[file].type] = [self.generators[file]]


        
        pass
    def ParseStaticRules(self, file):
        if os.path.exists(file):
            log.info(f"Applying network configuration from {file}")
            try:
                with open(file, "r") as f:
                    tc_commands = [line.strip() for line in f if line.strip() and not line.startswith('#')]

                for cmd in tc_commands:
                    log.debug(f"Running network command: {cmd}")
                    result = subprocess.run(cmd.split(), capture_output=True, text=True)
                    if result.returncode != 0:
                        log.error(f"Network command failed: {result.stderr}")
                    else:
                        log.debug(f"Network command output: {result.stdout}")
            except Exception as e:
                log.error(f"Failed to apply network configuration: {e}")
        else:
            log.info(f"No network configuration found at {file}")

    def ParseDynamicRules(self):
        '''
         make a subscriber for each generator type and call the generator function depending on the type
        '''

        for type in self.generatorstype:
            #create a subscriber for each generator type
            
            sub = NetworkPubSub(type)
            sub.subscribe(lambda ch, method, properties, body: CreateCallback(ch, method, properties, body, self.generatorstype[type]))
            self.Subscribers[type] = sub
        


def CreateCallback(ch,method,properties,body,generators,state=None):
    """
     create a callback function that iterates over all the generators for a specific type
    
     the generators are passed as a dictionary of generators with the index as the key
    """
    current_iter = int(body.decode('utf-8'))
    if state is None:
        state = {}
    
    # restructure the generatoer to be a dictionary of generators
    
    for key , gen in generators.items():
        if key not in state:
            state[key] = {}
        #check if the current iter is in the state
        if str(current_iter) in state[key]:
            for cmd in state[key][str(current_iter)]:
                log.debug(f"Executing command for time {current_iter}: {cmd}")
                result = subprocess.run(cmd.split(), capture_output=True, text=True)
                if result.returncode != 0:
                    log.error(f"Network command failed: {result.stderr}")
                else:
                    log.debug(f"Network command output: {result.stdout}")
        else:
            try:
                keygen, command = next(gen.generator)
                #save it in state if its not the current iter
                if keygen not in state[key]:
                    state[key][keygen] = []
                state[key][keygen].append(command)
            except StopIteration:
                # No more commands in the generator
                del generators[key]

    
import threading

class NetworkPubSub:

    connection = None
    channel = None
    topic = None

    HOST = None
    PORT = 6942

    def __init__(self,topic):
        '''
        input topic (epoch, time) 
        '''
        self.topic = topic
        self.connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=self.HOST, port=self.PORT))
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange='network', exchange_type='topic')

        self.consumer_thread = None
        self.running = False


    def subscribe(self, callback):
        '''
        given a callback function, subscribe to the topic and call the callback function when a message is received
        '''
        self.channel.queue_declare(queue="", durable=True)
        self.channel.queue_bind(exchange='network', queue="", routing_key=f'sync.{self.topic}')
        self.channel.basic_consume(queue="", on_message_callback=callback, auto_ack=True)
        log.info(f" [*] Waiting for messages in {self.topic} topic.")


        # Start consuming in a separate thread
        self.running = True
        self.consumer_thread = threading.Thread(target=self.consume_thread)
        self.consumer_thread.daemon = True  # Thread will exit when main program exits
        self.consumer_thread.start()
            
    def consume_thread(self):
        
        try:
            self.channel.start_consuming()
        except Exception as e:
            print(f"Consuming thread error: {e}")


    def stop_consuming(self):
        if self.running:
            self.running = False
            if self.channel and self.channel.is_open:
                self.channel.stop_consuming()
            if self.consumer_thread and self.consumer_thread.is_alive():
                self.consumer_thread.join(timeout=1.0)

    def publish(self, message):
        self.channel.basic_publish(exchange='network', routing_key=f'sync.{self.topic}',
                                    body=message, properties=pika.BasicProperties(
                                        delivery_mode=2,  # make message persistent
                                    ))
    def close(self):
        self.stop_consuming()
        if self.connection and self.connection.is_open:
            self.connection.close()
        




