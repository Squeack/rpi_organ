#!/usr/bin/python

import sys
import os.path
import time
import ConfigParser
import getopt
import paho.mqtt.client as mqtt

if __name__ == "__main__":
    DEBUG = False
    VERBOSE = False
    FIRSTTIME = 0

    # noinspection PyUnusedLocal
    def on_mqtt_connect(client, userdata, flags, rc):
        if rc == 0:
            global mqttconnected
            global mqtttopics
            global mqttclient
            global VERBOSE
            if VERBOSE:
                print("#Connected to MQTT broker")
            mqttconnected = True
            mqttclient.on_message = on_mqtt_message
            for t in mqtttopics:
                mqttclient.subscribe(t)
                if VERBOSE:
                    print "#Subscribing to {}".format(t)
        else:
            print("#MQTT connection failed. Error {} = {}".format(rc, mqtt.error_string(rc)))
            sys.exit(3)

    # noinspection PyUnusedLocal
    def on_mqtt_disconnect(client, userdata, rc):
        global mqttconnected
        global mqttclient
        mqttconnected = False
        if VERBOSE:
            print("#Disconnected from MQTT broker. Error {} = {}".format(rc, mqtt.error_string(rc)))
        # rc == 0 means disconnect() was called successfully
        if rc != 0:
            if VERBOSE:
                print("#Reconnect should be automatic")


    def connect_to_mqtt(broker, port):
        global mqttconnected
        global mqttclient
        if VERBOSE:
            print "#Connecting to MQTT broker at {}:{}".format(broker, port)
        mqttconnected = False
        mqttclient.on_connect = on_mqtt_connect
        mqttclient.on_disconnect = on_mqtt_disconnect
        mqttclient.loop_start()
        while mqttconnected is not True:
            try:
                mqttclient.connect(broker, port, 5)
                while mqttconnected is not True:
                    time.sleep(0.1)
            except:
                print "#Exception while connecting to broker"


    # noinspection PyUnusedLocal
    def on_mqtt_message(client, userdata, message):
        global frecord
        global FIRSTTIME
        global VERBOSE
        payload = message.payload
        now = time.time()
        if FIRSTTIME == 0:
            FIRSTTIME = now
        now -= FIRSTTIME
        data = "{:09.3f}:{}:{}".format(now, message.topic, payload)
        if VERBOSE:
            print data
        if frecord is not None:
            frecord.write(data+'\n')

    # Check command line startup options
    configfile = ""
    filename = ""
    frecord = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hdvc:f:", ["help", "debug", "verbose", "config=", "file="])
    except getopt.GetoptError:
        sys.exit(1)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print "Options are -d [--debug], -v [--verbose], -c [--config=]<configfile> -f [--file=]<playbackfile>"
            sys.exit(0)
        elif opt in ("-d", "--debug"):
            DEBUG = True
            print "#Debug mode enabled"
        elif opt in ("-v", "--verbose"):
            VERBOSE = True
            print "#Verbose mode enabled"
        elif opt in ("-c", "--config"):
            configfile = arg
            print "#Config file: {}".format(configfile)
        elif opt in ("-f", "--file"):
            filename = arg
            print "#Recording file: {}".format(configfile)

    if configfile == "":
        if os.path.isfile("~/.organ.conf"):
            configfile = "~/.organ.conf"
    if configfile == "":
        if os.path.isfile("/etc/organ.conf"):
            configfile = "/etc/organ.conf"
    if configfile == "":
        if os.path.isfile(sys.path[0] + "/organ.conf"):
            configfile = sys.path[0] + "/organ.conf"

    mqtttopics = []
    # Read config file
    try:
        if VERBOSE:
            print "#Using config file: {}".format(configfile)
        config = ConfigParser.SafeConfigParser()
        config.read(configfile)
        num_keyboards = config.getint("Global", "numkeyboards")
        this_keyboard = config.getint("Local", "thiskeyboard")
        mqttbroker = config.get("Global", "mqttbroker")
        mqttport = config.getint("Global", "mqttport")
        for k in range(0, num_keyboards):
            localsection = "Console" + str(k)
            mqtttopics.append(config.get(localsection, "topic"))
        if VERBOSE:
            print "#Found keyboards {}".format(mqtttopics)

    except ConfigParser.Error as e:
        print "#Error parsing the configuration file"
        print e.message
        sys.exit(2)

    if filename != "":
        frecord = open(filename, "w")

    mqttclient = mqtt.Client("Recorder")
    connect_to_mqtt(mqttbroker, mqttport)

    cont = True
    while cont:
        try:
            # Incoming messages are handled by the mqtt callback
            # No need to do anything here
            time.sleep(1)

        except KeyboardInterrupt:
            cont = False

    if VERBOSE:
        print "#Cleaning up"
        mqttclient.disconnect()
        mqttclient.loop_stop()
        if frecord is not None:
            frecord.close()
