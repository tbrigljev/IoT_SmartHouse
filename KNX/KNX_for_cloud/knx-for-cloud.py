# PYTHON3 KNX-CLIENT
# Brigljevic/GONZALEZ
# 09.2019

import sys
import socket
import time
import argparse
import textwrap

import datetime
import json
import os
import ssl
import jwt
import paho.mqtt.client as mqtt

from argparse import RawTextHelpFormatter    
from knxnet import *

######################################################################
## KNX DEDICATED FUNCTIONS ###########################################
## START #############################################################
######################################################################

## In the following code, "client" or "_cl" is the remote controller
## client and "gateway" or "_gt" points to the controlled device

def recv_data(sock):
    data_recv, addr = sock.recvfrom(1024)
    recv_data_object = knxnet.decode_frame(data_recv)
    return recv_data_object

def conn_req(sock, data_endpoint, control_endpoint, gateway_ip, gateway_port):
    conn_req_object = knxnet.create_frame(
        knxnet.ServiceTypeDescriptor.CONNECTION_REQUEST,
        data_endpoint, control_endpoint)
    conn_req_dtgrm = conn_req_object.frame
    sock.sendto (conn_req_dtgrm, (gateway_ip, gateway_port))

def conn_state_req(sock, channel_id, control_endpoint, gateway_ip, gateway_port):
    conn_state_req_object = knxnet.create_frame(
        knxnet.ServiceTypeDescriptor.CONNECTION_STATE_REQUEST,
        channel_id, control_endpoint)
    conn_state_req_dtgrm = conn_state_req_object.frame
    sock.sendto (conn_state_req_dtgrm, (gateway_ip, gateway_port))

def tunn_req(sock, dest_addr_group, channel_id, data, data_size, apci, gateway_ip, gateway_port):
    tunn_req_object = knxnet.create_frame(
        knxnet.ServiceTypeDescriptor.TUNNELLING_REQUEST,
        dest_addr_group, channel_id, data, data_size, apci)
    tunn_req_dtgrm = tunn_req_object.frame
    sock.sendto (tunn_req_dtgrm, (gateway_ip, gateway_port))

def tunn_ack(sock, channel_id, status, tunn_seq_count, gateway_ip, gateway_port):
    tunn_req_object = knxnet.create_frame(
        knxnet.ServiceTypeDescriptor.TUNNELLING_ACK,
        channel_id, status, tunn_seq_count)
    tunn_req_dtgrm = tunn_req_object.frame
    sock.sendto (tunn_req_dtgrm, (gateway_ip, gateway_port))

def disc_req(sock, channel_id, control_endpoint, gateway_ip, gateway_port):
    disc_req_object = knxnet.create_frame(
        knxnet.ServiceTypeDescriptor.DISCONNECT_REQUEST,
        channel_id, control_endpoint)
    disc_req_dtgrm = disc_req_object.frame
    sock.sendto (disc_req_dtgrm, (gateway_ip, gateway_port))

def KNX_rw(data_endpoint, control_endpoint, gateway_ip, gateway_port, group_address, payload):
    KNX_out = {}

##    print(data_endpoint)
##    print(control_endpoint)
##    print(gateway_ip)
##    print(gateway_port)
##    print(group_address)
##    print(payload)
    
    # Socket creation
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('',3672))

    # Sending connection request - Step 1
    conn_req(sock, data_endpoint, control_endpoint, gateway_ip, gateway_port)
    ##print("\nSending connection request...")

    # Recieving connection response - Step 2
    conn_gt_resp_object = recv_data(sock)
    conn_channel_id = conn_gt_resp_object.channel_id
    ##print("Connection open, channel ID is : {}".format(conn_channel_id))

    # Sending connection state request - Step 3
    conn_state_req(sock, conn_channel_id, control_endpoint, gateway_ip, gateway_port)
    ##print("\nSending connection state request...")

    # Recieving connection state response - Step 4
    conn_gt_resp_object = recv_data(sock)
    conn_state_resp = conn_gt_resp_object.status
    if conn_state_resp == 0:
        a = 0
        ##print("Connection status is {}, continuing...".format(conn_state_resp))
    else:
        ##print("Connection status is {}, exiting...".format(conn_state_resp))
        KNX_out = {'kErrorCode' : 'Connection status error : {}'.format(conn_state_resp)}
        return KNX_out

    # Sending tunnelling request - Step 5
    dest_addr_group = knxnet.GroupAddress.from_str(group_address)
    data, data_size, apci = payload[0], payload[1], payload[2]
    tunn_req(sock, dest_addr_group, conn_channel_id, data, data_size, apci, gateway_ip, gateway_port)
    ##print("\nSending tunnelling request...")

    # Receiving tunnelling acknowledgment - Step 6
    tunn_gt_ack_object = recv_data(sock)
    tunn_gt_ack_status = tunn_gt_ack_object.status
    if tunn_gt_ack_status == 0:
        a = 0
        ##print("Tunnelling status is {}, continuing...".format(tunn_gt_ack_status))
    else:
        ##print("Tunneling status is {}, exiting...".format(tunn_gt_ack_status))
        KNX_out = {'kErrorCode' : 'Tunnelling status error : '.format(tunn_gt_ack_status)}
        return KNX_out

    # Return of dataservice set as 0x2e (46) - Step 7
    tunn_gt_req_object = recv_data(sock)
    tunn_gt_data_service = tunn_gt_req_object.data_service
    tunn_gt_seq_count = tunn_gt_req_object.sequence_counter
    if tunn_gt_data_service == 46:
        a = 0
        ##print("\nGateway tunneling request is 0x{0:02x}, continuing...".format(tunn_gt_data_service))
    else:
        ##print("\nGateway tunneling request is not 0x(0:02x), exiting...".format(tunn_gt_data_service))
        KNX_out = {'kErrorcode' : 'Gateway tunnelling status error : '.format(tunn_gt_data_service)}
        return KNX_out

    # Sending tunnelling acknowledgment after successful comparison - Step 8
    tunn_cl_ack_status = 0
    tunn_ack(sock, conn_channel_id, tunn_cl_ack_status, tunn_gt_seq_count, gateway_ip, gateway_port)
    ##print("Sending tunnelling acknowledgment with status 0.")

    # When requesting state of blinds, second return of dataservice set
    if group_address[0] == '4':
        tunn_gt_req_object = recv_data(sock)
        tunn_gt_data = tunn_gt_req_object.data
        ##print("\nSecond gateway tunneling request (reading the state of the blinds)")
        ##print("The state of the blinds is {}, continuing...".format(tunn_gt_data))
        blind_id = 'blind{:02d}'.format(int(group_address.split('/')[2]))
        KNX_out = [blind_id, tunn_gt_data]

    # Sending disconnect request - Step 9
    disc_req(sock, conn_channel_id, control_endpoint, gateway_ip, gateway_port)
    ##print("\nSending disconnect request...")

    # Receiving disconnect response - Step 10
    disc_status = recv_data(sock).status
    ##print("Disconnect response status is {}, disconnecting...".format(disc_status))

    # Ending and exiting the script
    ##print("\nProtocol steps are complete. Have a nice day :)\n")
    time.sleep(1)
    if len(KNX_out) == 0:
        return {'kErrorCode' : 'Controlling devices successful'}
    return KNX_out

######################################################################
## KNX DEDICATED FUNCTIONS ###########################################
## END ###############################################################
######################################################################

######################################################################
## MQTT DEDICATED FUNCTIONS ##########################################
## START #############################################################
######################################################################

def create_jwt(project_id, private_key_file, algorithm):
    """Create a JWT (https://jwt.io) to establish an MQTT connection."""
    token = {
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
        'aud': project_id
    }
    with open(private_key_file, 'r') as f:
        private_key = f.read()
    print('Creating JWT using {} from private key file {}'.format(
        algorithm, private_key_file))
    return jwt.encode(token, private_key, algorithm=algorithm)


def error_str(rc):
    """Convert a Paho error to a human readable string."""
    return '{}: {}'.format(rc, mqtt.error_string(rc))

######################################################################
## MQTT DEDICATED FUNCTIONS ##########################################
## END ###############################################################
######################################################################

def parse_command_line_args():
   
    parser = argparse.ArgumentParser(
        description = 'Google Cloud IoT MQTT device connection code',
        formatter_class = RawTextHelpFormatter)
    
    parser.add_argument(
        'project_id',
        help = 'Google Cloud project name')
    
    parser.add_argument(
        'registry_id',
        help = 'Cloud IoT registry ID')

    parser.add_argument(
        'device_id',
        help = 'Cloud IoT device ID')

    parser.add_argument(
        'topic',
        help = 'Cloud Pub/Sub topic')

    parser.add_argument(
        'private_key_file',
        help = 'Path to private key file')

    parser.add_argument(
        'algorithm',
        choices = ['RS256', 'ES256'],
        help = 'Encryption algorithm to use to generate the JWT')

    parser.add_argument(
        '--cloud_region',
        default = 'europe-west1',
        help = 'Google Cloud region (default: eu-west1)')

    parser.add_argument(
        '--ca_certs',
        default = 'roots.pem',
        help = textwrap.dedent('''\
        CA root certificate (default: roots.pem)
        Get from https://pki.google.com/roots.pem'''))

    parser.add_argument(
        '--num_messages',
        type = int,
        default = 100,
        help = 'Number of message to publish (default: 100)')

    parser.add_argument(
        '--mqtt_bridge_hostname',
        default = 'mqtt.googleapis.com',
        help = 'MQTT bridge hostname (default: mqtt.googleapis.com)')

    parser.add_argument(
        '--mqtt_bridge_port',
        type = int,
        default = 8883,
        help = 'MQTT bridge port (default: 8883)')

    parser.add_argument(
        '--message_type',
        choices = ['event', 'state'],
        default = 'event',
        help = textwrap.dedent('''\
        Indicates whether the message to be published is a:
        - Telemetry event (default)
        - Device state message'''))
    
    return parser.parse_args()

class Device(object):
    def __init__(self):

        self.init = 0
        self.connected = False
        self.room = -1

        self.blinds_targets = ''
        self.valves_targets = ''
        
        self.data_endpoint = ''
        self.control_endpoint = ''
        self.gateway_ip = ''
        self.gateway_port = ''
        self.group_address = ''
        self.payload = ''

        self.blinds = [-1]
        self.valves = [-1]
        
        self.KNX_out = {'kErrorCode' : 'Waiting on initialisation'}
        self.KNX_err = -1
        self.KNX_data = -1

    def general_output(self):
        print('Init : {}'.format(self.init))
        print('Connected : {}'.format(self.connected))

        print('Blinds tgt : {}'.format(self.blinds_targets))
        print('Valves tgt : {}'.format(self.valves_targets))

        print('Data endpoint : {}'.format(self.data_endpoint))
        print('Ctrl endpoint : {}'.format(self.control_endpoint))
        print('Gateway IP : {}'.format(self.gateway_ip))
        print('Gateway port : {}'.format(self.gateway_port))
        print('Group addr : {}'.format(self.group_address))
        print('Payload : {}'.format(self.payload))

        print('Blinds : {}'.format(self.blinds))
        print('Valves : {}'.format(self.valves))

        print('OUT : {}'.format(self.KNX_out))
        print('ERR : {}'.format(self.KNX_err))
        print('DATA : {}'.format(self.KNX_data))

    def update(self, **kwargs):
        kwargs.setdefault('data_endpoint', self.data_endpoint)
        data_endpoint = kwargs['data_endpoint']
        
        kwargs.setdefault('control_endpoint', self.control_endpoint)
        control_endpoint = kwargs['control_endpoint']
        
        kwargs.setdefault('gateway_ip', self.gateway_ip)
        gateway_ip = kwargs['gateway_ip']
        
        kwargs.setdefault('gateway_port', self.gateway_port)
        gateway_port = kwargs['gateway_port']
        
        kwargs.setdefault('group_address', self.group_address)
        group_address = kwargs['group_address']
        
        kwargs.setdefault('payload', self.payload)
        payload = kwargs['payload']
        
        return KNX_rw(
            data_endpoint,
            control_endpoint,
            gateway_ip,
            gateway_port,
            group_address,
            payload)

    def update_setpoints(self):
        for blinds_target, blinds_val in zip(self.blinds_targets, self.blinds):
            self.group_address = '3/' + blinds_target
            self.payload = [blinds_val, 2, 2]
            self.update(group_address = self.group_address, payload = self.payload)
        
        for valves_target, valves_val in zip(self.valves_targets, self.valves):
            self.group_address = '0/' + valves_target
            self.payload = [valves_val, 2, 2]
            self.update(group_address = self.group_address, payload = self.payload)
            
        self.KNX_out = {'kErrorCode' : 'CONFIGURATION UPDATED'}
        self.init = 1

    def room_config(self):

        for blinds_target, blinds_val in zip(self.blinds_targets, self.blinds):
            self.group_address = '3/' + blinds_target
            self.payload = [blinds_val, 2, 2]
            self.update(group_address = self.group_address, payload = self.payload)
        
        for valves_target, valves_val in zip(self.valves_targets, self.valves):
            self.group_address = '0/' + valves_target
            self.payload = [valves_val, 2, 2]
            self.update(group_address = self.group_address, payload = self.payload)

        self.KNX_out = {'kErrorCode' : 'CONFIGURATION UPDATED'}

    def read_message(self, payload):
        
        if payload['type'] == 'config':
            knx_gateway = payload['gateway']
            knx_endpoint = payload['endpoint']

            self.gateway_ip = knx_gateway.split(':')[0]
            self.gateway_port = int(knx_gateway.split(':')[1])
            endpoint_ip, endpoint_port = [addr for addr in knx_endpoint.split(':')]

            self.data_endpoint = (endpoint_ip, int(endpoint_port))
            self.control_endpoint = (endpoint_ip, int(endpoint_port))

            self.blinds_targets = payload['targets']['blinds']['id']
            self.valves_targets = payload['targets']['valves']['id']
            
            if self.blinds == [-1]:
                self.blinds = payload['targets']['blinds']['val']
            if self.valves == [-1]:
                self.valves = payload['targets']['valves']['val']

            self.room_config()

            print()
            print("Target(s) :           {:>15}:{:>4}".format(self.gateway_ip, self.gateway_port))
            print("Data endpoint(s) :    {:>15}:{:>4}".format(endpoint_ip, endpoint_port))
            print("Control endpoint(s) : {:>15}:{:>4}".format(endpoint_ip, endpoint_port))
            print("*****Configuring for {} blinds and {} valves.*****"
                  .format(len(self.blinds_targets), len(self.valves_targets)))

        if payload['type'] == 'update':
            set_blinds = list(payload['data']['blinds'])
            for i in range(len(set_blinds)):
                if(set_blinds[i] != -1):
                    self.blinds[i] = set_blinds[i]
            set_valves = list(payload['data']['valves'])
            for i in range(len(set_valves)):
                if(set_valves[i] != -1):
                    self.valves[i] = set_valves[i]

            self.update_setpoints()
            print()
            print("*****Configuring blinds with data {} and valves with data {}.*****"
                  .format(self.blinds, self.valves))

    def wait_for_connection(self, timeout):
        total_time = 0
        while not self.connected and total_time < timeout:
            time.sleep(1)
            total_time += 1
        if not self.connected:
            raise RuntimeError('Could not connect to MQTT bridge.')

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        print('Connection result: ', error_str(rc))
        self.connected = True

    def on_disconnect(self, unused_client, unused_userdata, rc):
        print('Disconnected: ', error_str(rc))
        self.connected = False

    def on_publish(self, unused_client, unused_userdata, unused_mid):
        print('Published message acknowledged (PUBACK received).')

    def on_subscribe(self, unused_client, unused_userdata, unused_mid, granted_qos):
        print('Subscribed: ', granted_qos)
        if granted_qos[0] == 128:
            print('Subscription failed.')

    def on_message(self, unused_client, unused_userdata, message):

        raw_payload = message.payload.decode('utf-8')

        if raw_payload == '':
            print('No message received yet, waiting...')
            return 0
        else:
            payload = json.loads(raw_payload)
            if(self.room != payload['room']):
                print('No message targetting this room received yet, waiting...')
                return 0
            else:
                print('Received message :\n\'{}\'\n   on topic : \'{}\'\n   with QOS : {}'.
                      format(raw_payload, message.topic, str(message.qos)))
                ##payload = json.loads(raw_payload)
                if self.init == 0:
                    self.init = 1

                self.read_message(payload)

                self.KNX_err = self.KNX_out[0]
                self.KNX_data = self.KNX_out[1] if len(self.KNX_out) > 1 else 'EMPTY'

def main():
    
    args = parse_command_line_args()

    client = mqtt.Client(
        client_id = 'projects/{}/locations/{}/registries/{}/devices/{}'.format(
            args.project_id, args.cloud_region, args.registry_id, args.device_id))
    client.username_pw_set(
        username = 'unused',
        password = create_jwt(
            args.project_id, args.private_key_file, args.algorithm))
    client.tls_set(ca_certs = args.ca_certs, tls_version = ssl.PROTOCOL_TLSv1_2)

    device = Device()

    client.on_connect = device.on_connect
    client.on_publish = device.on_publish
    client.on_disconnect = device.on_disconnect
    client.on_subscribe = device.on_subscribe
    client.on_message = device.on_message

    client.connect(args.mqtt_bridge_hostname, args.mqtt_bridge_port)

    client.loop_start()

    mqtt_telemetry_topic = '/devices/{}/events/{}'.format(args.device_id, args.topic)
    mqtt_config_topic = '/devices/{}/config'.format(args.device_id)
    device.wait_for_connection(5)
    client.subscribe(mqtt_config_topic, 0)
    device.room = int(args.topic[-2])

    device.init = 0

    i = 1
    try:
        while True:
            print("{}\nEntering infinite loop - #{}\n{}".format('-'*20, i, '-'*20))
            i += 1
            time.sleep(5)
            payload_command_blinds = ''
            ##############################################################
            ## Waiting for the first configuration message
            if device.init == 0:
                print('There is no configuration for this device. Waiting...')
                while device.init == 0:
                    payload = json.dumps({
                        'kErrorCode' : 'NO CONFIGURATION'})
                    client.publish(mqtt_telemetry_topic, payload, qos = 1)
                    time.sleep(10)
                continue
            ##############################################################
            ## Confirming configuration
            if device.init == 1:
                print('Sending configuration confirmation')
                payload = json.dumps(device.KNX_out)
                client.publish(mqtt_telemetry_topic, payload, qos = 1)
                device.init = 2
                time.sleep(2)
                continue
            ##############################################################
            ## Sending blinds and valves status
            if device.init == 2:
                ##device.general_output()
                payload_current_status = {}
                for blinds_targets, blinds_val in zip(device.blinds_targets, device.blinds):
                    blind_status = {}
                    knx_out = device.update(group_address = '4/' + blinds_targets, payload = [blinds_val, 2, 2])
                    blind_status['set_val'] = blinds_val
                    blind_status['real_val'] = knx_out[1]
                    payload_current_status[knx_out[0]] = blind_status
                for valves_target, valves_val in zip(device.valves_targets, device.valves):
                    valve_status = {}
                    valve_id = 'valve{:02d}'.format(int(valves_target.split('/')[1]))
                    valve_status['set_val'] = valves_val
                    valve_status['real_val'] = valves_val
                    payload_current_status[valve_id] = valve_status

                payload_current_status['kErrorCode'] = 'CURRENT STATUS'
                payload = json.dumps(payload_current_status)
                print('Publishing payload : {}'.format(payload))
                client.publish(mqtt_telemetry_topic, payload, qos = 1)
                time.sleep(5)            
            ##############################################################
            ## Requesting command updates (automatic and manual)
            if device.init == 2:
                print('Requesting command update')
                payload = json.dumps({'kErrorCode' : 'WAITING ON COMMAND'})
                client.publish(mqtt_telemetry_topic, payload, qos = 1)
                time.sleep(10)

    except KeyboardInterrupt:
        print('\nRe-initialising device configuration')
        payload = json.dumps({'kErrorCode' : 'INTERRUPT REINIT'})
        client.publish(mqtt_telemetry_topic, payload, qos = 1)
        print('Re-initialisation done. Exiting.')
        client.disconnect()
        client.loop_stop()

###################################################

if __name__ == '__main__':
    main()































    
