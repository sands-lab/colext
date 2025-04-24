# TODO:
'''
1- make a class for pub sub
2- make a class for the rules and make it have a generator for the commands
3- the second class should accept either script or json file as input


'''

import pika


class NetworkGenerator:

    generator = None


    def __init__(self,type,file):
        '''
        accept type (script or json) and file (path to the file)
        and create the generator based on the type
        '''
        pass    
    def json_parser():
        '''
        given an input json file, parse it and create a dictionary of rules
        '''
        pass
    def converter():
        '''
        given an input rule and struct convert it to a command line string
        '''
        pass
    def generator():
        '''
        given an input type and dict
        if type normal, make a generator for the input list of rules
        if type is script, wrap the script with a generator and call the init function
        and return the generator object
        '''

        pass
    

    def get_generator(self):
        '''
        return the generator object
        '''
        pass

    

class NetworkManager:

    # dict of generators for all dynamic rules, key is type and value is the generator object
    Generators = {}

    def __init__(self,folder_path="network/"):
        '''
        parse the static rules and dynamic rules and create the generators

        '''
        pass
    def MakeNetworkGenerator(self, generator_type, file):
        pass
    def ParseStaticRules(self, file):
        pass
    def ParseDynamicRules(self, file):
        pass

    


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


        pass
    def subscribe(self, callback):
        '''
        given a callback function, subscribe to the topic and call the callback function when a message is received
        '''
        self.channel.queue_declare(queue="", durable=True)
        self.channel.queue_bind(exchange='network', queue="", routing_key=f'sync.{self.topic}')
        self.channel.basic_consume(queue="", on_message_callback=callback, auto_ack=True)
        self.channel.start_consuming()


        pass
    def publish(self, topic, message):
        self.channel.basic_publish(exchange='network', routing_key=f'sync.{topic}',
                                    body=message, properties=pika.BasicProperties(
                                        delivery_mode=2,  # make message persistent
                                    ))
    def close(self):
        self.connection.close()
        




