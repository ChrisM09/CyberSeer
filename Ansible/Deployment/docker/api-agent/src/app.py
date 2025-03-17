from ast import literal_eval
import json
import logging
from flask import Flask, request, Response, make_response, jsonify

# Paho MQTT python library.
from paho.mqtt.enums import MQTTProtocolVersion
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt

# Time imports needed to timeout the old MQTT messages
import time
import datetime
import threading
    
# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

# Timeout used to denote an old check.
PUBLISH_REPORT_TIMEOUT = 45

app = Flask(__name__)

@app.route('/publish-checks', methods=['POST'])
def publish_checks():
    """
        Publish a given check from main scoring engine.
        
        Publishes the URL to download from.
            URL = <IP>/checks/<Check-Name>  
            
            
        Args:
            - checks: List of checks that are given.
                - target-agent: Who the check is reserved for (DNS name)
                - target-script: Which check script to run
                - arglist: List of extra arguments given.
            - repo-IP: <IP address>
            - run-method: [ python | bash | ps1 | sh ]            
              
    """
    
    # Now, parse out the information that was sent.
    req = request.get_json()
    print(f"Request: {req}")
    
    # Parse out the important information
    list_of_checks = req.get('checks', [])
    repo_ip = req.get('repo-ip', "")

    # So now, we have all the information that we need to
    # start publishing to the MQTT topic for checks.
    
    # Create an array to publish multiple messages at once.
    # Multiple small json dictionaries that is.
    messages = []
    
    for check in list_of_checks:
        
        # Convert the random bytes in here to a dictionary that can be parsed.
        mqtt_data = {
            "agent": check["target-agent"],
            "downloadURL": f"http://{repo_ip}:8080/checks/{check["target-script"]}",
            "msgtype": "check", # TODO: If it needs to be refreshed, then let everyone know.
            "run-method": check['run-method'],
            "arg-list": check['arg-list']
        }
        
        mqtt_data = json.dumps(mqtt_data)
        messages.append({'topic': "checks", 'payload': mqtt_data})


    # Now, publish these checks.
    publish.multiple(messages, hostname="mqtt-server", port=1883, protocol=MQTTProtocolVersion.MQTTv5)
    return Response("Checks have been published.", status=200)
    

@app.route('/read-result', methods=['POST'])
def read_result():
    """
    Read a result from the MQTT topic that's specified from the
    body of the POST request given from the main scoring engine.
    
    NOTE: The MQTT server is on a Docker Swarm that this API will be a part of,
    so we can use the Docker hostname on it.       
    
    Args:
        - target-topic : the desired topic to read from.
    """
    
    logging.debug("Received a request to /read-result")
    
    # Parse out the information in the body.
    req = request.get_json()
    target_agent = req.get('reporting-agent')
    target_check = req.get('check-ran')
    arg_list = req.get('arg-list')
    # target_topic = f'{target_agent}-{target_check}-{'-'.join(arg_list)}-result'

    target_topic = f"{target_agent}-{target_check}-{'-'.join(arg_list[0].split())}-result"


    logging.debug(f"Information contained within the request:\n"
                 f"\tAgent looking for: {target_agent}\n"
                 f"\tCheck supposed to run: {target_check}\n"
                 f"\tTopic supposed to read from: {target_topic}") 
    
    if not target_topic or not target_agent or not target_check:
        logging.error("Missing required parameters in the request")
        return jsonify({"error": "Missing required parameters"}), 400
    
    result_event = threading.Event()
    mqtt_message = {'description': None, 'status': None}

    # Define the callback function for when a message is received
    def on_message(client, userdata, message):
        try:
            message_payload = message.payload.decode('utf8')
            # logging.info(f"Received MQTT message: {message_payload}")
            json_message = json.loads(message_payload)
        
            # Get the last timestamp and check it against the current time.
            last_timestamp = json_message['timestamp']
            logging.debug(f"Timestamp included in the message: {last_timestamp}")

            # Cast them to structs that can do arithmetic operations.
            last_timestamp = time.mktime(datetime.datetime.strptime(last_timestamp, "%Y-%m-%d %H:%M:%S.%f").timetuple())
            cur_timestamp = time.mktime(datetime.datetime.now().timetuple())
            logging.debug(f"Time difference: {cur_timestamp - last_timestamp}")

            if cur_timestamp - last_timestamp > PUBLISH_REPORT_TIMEOUT:
                result_code = 406
                mqtt_message['description']= "Old MQTT message detected. Is the target agent running?"
                mqtt_message['status'] = result_code
                logging.debug(f"Old MQTT message detected. Is the target agent running?")
                result_event.set()
            elif (json_message['reporting-agent'] == target_agent and json_message['check-ran'] == target_check):
                result_code = 200 if json_message['exit-code'] == 0 else 406
                mqtt_message['description'] = json_message['description']
                mqtt_message['status'] = result_code
                logging.debug(f"Setting result event with message: {mqtt_message}")
                result_event.set()
        except Exception as e:
            logging.exception(f"Exception occurred in the on_message callback: {e}")
        finally:
            client.disconnect()

    # Define the callback function for when the client connects to the broker
    def on_connect(client, userdata, flags, reason_code, properties=None):
        logging.info(f"Connected to MQTT broker with result code {reason_code}")
        client.subscribe(target_topic)

    # Create an MQTT client instance
    client = mqtt.Client()
    client.on_message = on_message
    client.on_connect = on_connect

    # Connect to the broker
    try:
        client.connect("mqtt-server", 1883, 60)
        logging.info("MQTT client connected to broker")
    except Exception as e:
        logging.exception(f"Failed to connect to MQTT broker: {e}")
        return jsonify({"error": "Failed to connect to MQTT broker"}), 500
    
    client.loop_start()

    # Wait for the result event to be set by the on_message callback
    if not result_event.wait(timeout=20):  # Wait up to 20 seconds for a message.
        logging.warning("Timeout waiting for MQTT message")
    
    client.loop_stop()

    if mqtt_message['description'] is not None:
        logging.info(f"Returning response with message: {mqtt_message}")
        return Response(response=mqtt_message['description'], status=mqtt_message['status'])
    else:
        logging.warning("No relevant message received or timed out")
        return jsonify({"error": "No relevant message received or timed out"}), 408

if __name__ == '__main__':
    app.run('0.0.0.0')
