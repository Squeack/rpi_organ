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
            global VERBOSE
            if VERBOSE:
                print("#Connected to MQTT broker")
            mqttconnected = True
        else:
            print("#MQTT connection failed")
            sys.exit(3)


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

    topics = []
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
            topics.append(config.get(localsection, "topic"))
        if VERBOSE:
            print "#Found keyboards {}".format(topics)

    except ConfigParser.Error as e:
        print "#Error parsing the configuration file"
        print e.message
        sys.exit(2)

    if filename != "":
        frecord = open(filename, "w")

    if VERBOSE:
        print "#Connecting to MQTT broker at {}:{}".format(mqttbroker, mqttport)
    mqttclient = mqtt.Client("Recorder")
    mqttclient.on_connect = on_mqtt_connect
    mqttclient.on_message = on_mqtt_message
    mqttconnected = False
    mqttclient.connect(mqttbroker, mqttport, 30)
    mqttclient.loop_start()
    while mqttconnected is not True:
        time.sleep(0.1)
    for t in topics:
        mqttclient.subscribe(t)
        if VERBOSE:
            print "#Subscribing to {}".format(t)

    cont = True
    while cont:
        try:
            # Incoming messages are handled by the mqtt callback
            time.sleep(1)

        except KeyboardInterrupt:
            cont = False

    if VERBOSE:
        print "#Cleaning up"
        mqttclient.disconnect()
        mqttclient.loop_stop()
        frecord.close()
