import copy
import dns.resolver
import json # Parse JSON? -- Reading the things will be dictionaries so it should not be needed
import logging
import logging.handlers
import os
import paho.mqtt.client as mqtt # This is the library arbitraily chosen to serve as the MQTT agent
import requests
import sys # System Interaction, exit
import subprocess # Process Managment and Communcation
import socket
from threading import Lock, Thread
import datetime
import time



# Logging
logger = logging.getLogger("End_Agent")
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
# 20 MB file limit with 1 backup
ch = logging.handlers.RotatingFileHandler('agent.log', maxBytes=2000000, backupCount=1)
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class Agent:
    """
        Agent class is the main class that will be used to run the agent.
        This contains once function that should be ran by an external user
        `run` All others are internal and should not be called outside of
        the class.
    """
    def __init__(self):

        # Array to contains DNS associations.
        self.dns_associations = []

        # Mutex List for refreshing topics
        self.mut_list = []
        # List of checks, we add to it when we
        # see a new check, the idex allows us to
        # associate a mutex with the
        self.chk_list = []

        # Init MQTT client object
        self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # Use Version2 for most up-to-date paho-mqtt clients, bettwen with MQTTv3 and 5

        # Configure MQTT Agent (Done Once)
        self.mqttc.on_connect = self. on_connect
        self.mqttc.on_message = self.on_message
        self.mqttc.on_subscribe = self.on_subscribe
        self.mqttc.on_unsubscribe = self.on_unsubscribe

        # Setup agent configuration and association
        self.read_agent_configuration()

    def run(self):
        """
            Run the agent. This is what will carry out all the functions.
        """

        # Connect, Subscriptions are made on connection
        self.mqttc.connect(self.mqtt_broker, self.mqtt_port)

        # Loop Forever
        self.mqttc.loop_forever()

    def on_subscribe(self,client, userdata, mid, reason_code_list, properties):
        """
        Callback function for paho-MQTT when subscribing to a topic.
        """

        # The Agent will be subscribing to only one topic "checks"
        # This means we will only have one reason responce.
        # In the event this is modified to handle multiple we
        # may as well loop.
        for responce in reason_code_list:
            # If the responce is a failure, we have a large problem.
            # Should probably add logging at some point -- Matt
            if responce.is_failure:
                logger.error(f"Broker rejected your subscription: {responce}")
            else:
                logger.info(f"Broker granted the following QoS level: {responce.value}")
        return

    def on_unsubscribe(self, client, userdata, mid, reason_code_list, properties):
        """
        Callback function for paho-MQTT when unsubscribing to a topic.

        In the event we unsubscribe we will need to kill the agent because it no
        longer has a purpose. If this has childern we need to consider
        and kill those too.
        """

        # Bad
        if len(reason_code_list) == 0:
                logger.info("unsubscribe succeeded (if SUBACK is received in MQTTv3 it success)")
                self.client.disconnect()
                sys.exit()
                # Never Get Here

        # The Agent will be subscribing to only one topic "checks"
        # This means we will only have one reason responce.
        # In the event this is modified to handle multiple we
        # may as well loop.
        for responce in reason_code_list:
            # If the responce is a failure, we have a large problem.
            # Should probably add logging at some point -- Matt
            if  not responce.is_failure:
                logger.info("unsubscribe succeeded (if SUBACK is received in MQTTv3 it is a success)")
            else:
                logger.error(f"Broker replied with failure: {reason}")

        # We are done, so we should exit!
        self.client.disconnect()
        sys.exit()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        """
        This is the callback function which is done every time the client connects to the MQTT server
        """
        if reason_code.is_failure:
            logger.error(f"Failed to connect: {reason_code}. The loop_forever() function will retry connection")
            return

        # we should always subscribe from on_connect callback to be sure
        # our subscribed is persisted across reconnections.
        for topic in self.sub_topic_list:
            client.subscribe(topic)


    def on_message(self, client, userdata, message):
        """
        Every time the Topic gets a new message, the client is notified and this callback function will be executed
        """
        # Index of the last slash, default to 0
        sindex = 0

        # If we have a message from a topic we subscribed to
        if message.topic in self.sub_topic_list:

            # Load JSON message into python dictionary
            try:
                jmessage = json.loads(message.payload.decode('utf8'))

                # Reverse DNS lookup did not work with PiHole.
                # Need to do a forward lookup each time there is a new check that comes in.
                # We're not worried about performance at the moment.
                # Potential scalability issue.

                my_resolver = dns.resolver.Resolver()
                my_resolver.nameservers = [self.dns_server]  #set name servers seperated by comma
                ipaddy = jmessage['agent']

                try:
                    result = my_resolver.resolve(ipaddy, "A")[0]
                except Exception as e:
                    logger.info(f"DNS not for me... ignore this check")
                    return

                # Get the IP addresses that are associated with this host.
                ip_address = self.get_ip_addresses()
                logger.info(ip_address)

                # Check if my IP is in the answer.
                if(ip_address != result.address):
                    logger.info(f"Received message for {jmessage['agent']}: Skipping check at URL {jmessage['downloadURL']}")
                    return

                # Parse out Script name from URL (Last chunk?)
                sindex = (jmessage['downloadURL'].rfind("/"))

                # This is a failure case.
                if sindex == -1:
                    self.agent_failure("Error Parsing out command name")
                    logger.error(f"Error Parsing out command name from {jmessage['downloadURL']}")
                    return

                # substr Out command Name from URL
                commandName = (jmessage['downloadURL'])[sindex+1:]

                # Mutual Exclusion Setup, we will use the index into chk_list to find the correct mutex...
                # we only do this if it has not been done before.
                if commandName not in self.chk_list:
                    self.mut_list.append(Lock())
                    self.chk_list.append(commandName)


                # If this is a check we need to handle check based operations
                if jmessage['msgtype'] == self.check_type_name:

                    # Always call this, users may delete the files or they may be removed
                    # it should immediately return a success if they already exist
                    if (self.download_check_script(jmessage['downloadURL'], commandName) == -1):
                        self.agent_failure("Error in downloading script")
                        logger.error(f"Error in downloading script: {jmessage['downloadURL']}")
                        return

                    # We run the check... This will internally parse the check's file name
                    # This function will handle updating the responce to the MQTT server too
                    self.run_check_script(commandName, jmessage['arg-list'], jmessage['agent'])

                # If this is a refresh message we need to handle refresh (of file) operations
                elif jmessage['msgtype'] == self.refresh_type_name:

                    if (self.refresh_check_script(jmessage['downloadURL'], commandName) == -1):
                        self.agent_failure("Failure to refresh script")
                        logger.error(f"Error in refreshing script: {jmessage['downloadURL']}")

                    return

            except Exception as e:
                self.agent_failure("Error in parsing message to JSON invalid MQTT body received")
                logger.error("Error in parsing message to JSON")
                return

        else:
            # This should not be possible but we should take care
            self.agent_failure("Unknown message topic received")
            logger.error(f"Unknown topic received: {message.topic}")
            return

    def refresh_check_script(self, checkURL, commandName):
        res = 0
        # Claim mutex to prevent overwriting files while in use
        with self.mut_list[self.chk_list.index(commandName)]:
            try:
                # Setup Directory
                if(not os.path.exists("./tmp/")):
                    os.mkdir("tmp/")

                chrsp = requests.get(checkURL)

                with open("./tmp/"+commandName, "wb") as f:
                    f.write(chrsp.content)
            except Exception as e:
                res = -1
        return res

    def download_check_script(self, checkURL, commandName):
        """
            Download the check script that is associated with the check.

            Likely going to be a get request.
        """
        res = 0
        # Refresh would be handled elsewhere we just need to make
        # sure we do not start messing with the files while they are
        # being executed

        # Claim Mutex for function?
        with self.mut_list[self.chk_list.index(commandName)]:

            try:
                # Setup Directory
                if(not os.path.exists("./tmp/")):
                    os.mkdir("tmp/")

                # Get the check script from the check_repo.
                # The check script will be a python script that will be run on the agent.
                if not (os.path.exists("./tmp/"+commandName)):
                    chrsp = requests.get(checkURL)

                    with open("./tmp/"+commandName, "wb") as f:
                        f.write(chrsp.content)
            except Exception as e:
                res = -1
        # There is a better way.
        return res

    def get_ip_addresses(self):
        """
            Get the IP addresses that are associated with this host.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('8.8.8.8', 80))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def read_agent_configuration(self):
        """
            Read the agent configuration file that is located in the agent_config directory.

            The configuration file is a JSON file that will contain important information about how the agent
            will go about its operations.
        """

        with open('agent_config/agent_config.json', 'r') as f:
            agent_config = json.load(f)

            # Now, we need to parse the agent configuration file.
            # Find the MQTT broker information.
            self.mqtt_broker = agent_config['mqtt_broker']

            # Get the MQTT port.
            self.mqtt_port = agent_config['mqtt_port']

            # Paranoia to make sure we have an int.
            if not isinstance(self.mqtt_port, int):
                self.mqtt_port = int(self.mqtt_port)

            # String we search for when dealing with check messages;
            # This could be made different from the topic's name.
            self.check_type_name = agent_config['message_type_check']

            # String we search for when dealing with refresh messages;
            # This could be made different from the topic's name.
            self.refresh_type_name = agent_config['message_type_refresh']

            # Get the MQTT topic list.
            # This is a list of topics that we should
            # subscribe to and handle messages from
            self.sub_topic_list = agent_config['mqtt_sub_topic_list']

            # This is a **CONSTANT** describing the index
            # We will find the 'check' topic's identifier at.
            self.check_topic_num = agent_config['check_topic_num']

            # This is a list of topics that we should
            # Publish to.
            self.pub_topic_list = agent_config['mqtt_pub_topic_list']

            # This is a **CONSTANT** describing the index
            # We will find the 'results' topic's identifier at.
            self.pub_topic_num = agent_config['pub_topic_num']

            # Get the location of the blue team DNS server.
            self.dns_server = agent_config['dns_server']

    def run_check_thread(self, command, arglist, agent):
        logger.info("Reached run_check_thread")

        try:
            true_arglist = copy.deepcopy(arglist)


            # Reassign arglist by splitting any space-separated strings in true_arglist
            arglist = []
            for arg in true_arglist:
                arglist.extend(arg.split())  # Split strings and add elements individually to arglist

            # Create Subprocess and PIPE for communcation
            arglist.insert(0,"tmp/"+command)
            arglist.insert(0,"python3") # Hodge Podge

            check_process = subprocess.Popen(arglist, stdout=subprocess.PIPE) # May need to invoke Python Interpriter

            # Parse Results and Create message
            check_data = (check_process.communicate()[0]).decode("utf-8")
            check_rc = check_process.returncode

            # Timestamp needed for the retain argument
            now = str(datetime.datetime.now())

            data = {'reporting-agent':agent,
                    'check-ran':command,
                    'exit-code':check_rc,
                    'description': check_data,
                    'timestamp': now}

            msg = json.dumps(data)

            # This will return a Message Info Class, I ignore this because there
            # is not much we can do if the message fails to send (ADD LOGGING)
            #self.mqttc.publish(self.pub_topic_list[self.pub_topic_num], msg, qos=1)

            topic_to_publish_to = f"{agent}-{command}-{'-'.join(true_arglist[0].split())}-result"
            logger.info(f"Publishing info to: {topic_to_publish_to}" )


            # logger.info(f"Publishing info to: {agent}-{command}-{'-'.join(true_arglist)}-result" )
            # self.mqttc.publish(f"{agent}-{command}-{'-'.join(true_arglist)}-result", msg, qos=1, retain=True)
            self.mqttc.publish(topic_to_publish_to, msg, qos=1, retain=True)

        except Exception as e:
            self.agent_failure('Failure in running score check')

    def run_check_script(self, command, arglist, agent):
        """
            Run the script that was downloaded from the script-repo.

        """

        logger.info("Reached run_check_script")

        thread = Thread(target=self.run_check_thread, args=(command, arglist, agent), daemon=False)
        thread.start()

    def agent_failure(self, MSG):
        # Agent Failure
        msg = json.dumps({'reportingagent':self.dns_associations, 'check-ran':"AgentFailure", 'exit-code': 99999,  'description': MSG})

        # This will return a Message Info Class, I ignore this because there
        # is not much we can do if the message fails to send (ADD LOGGING)
        self.mqttc.publish(self.pub_topic_list[self.pub_topic_num], msg, qos=1)


if __name__ == "__main__":

    # Run the agent.
    Agent().run()
