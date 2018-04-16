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
    STARTTIME = 0

    # noinspection PyUnusedLocal
    def on_mqtt_connect(client, userdata, flags, rc):
        if rc == 0:
            global mqttconnected
            global VERBOSE
            if VERBOSE:
                print("Connected to MQTT broker")
            mqttconnected = True
        else:
            print("MQTT connection failed. Error {} = {}".format(rc, mqtt.error_string(rc)))
            sys.exit(3)

    # noinspection PyUnusedLocal
    def on_mqtt_disconnect(client, userdata, rc):
        global mqttconnected
        global mqttclient
        mqttconnected = False
        if VERBOSE:
            print("Disconnected from MQTT broker. Error {} = {}".format(rc, mqtt.error_string(rc)))
        # rc == 0 means disconnect() was called successfully
        if rc != 0:
            if VERBOSE:
                print("Reconnect should be automatic")

    def connect_to_mqtt(broker, port):
        global mqttconnected
        global mqttclient
        if VERBOSE:
            print "Connecting to MQTT broker at {}:{}".format(broker, port)
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
                print "Exception while connecting to broker"

    # Check command line startup options
    configfile = ""
    filename = ""
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
            print "Debug mode enabled"
        elif opt in ("-v", "--verbose"):
            VERBOSE = True
            print "Verbose mode enabled"
        elif opt in ("-c", "--config"):
            configfile = arg
            print "Config file: {}".format(configfile)
        elif opt in ("-f", "--file"):
            filename = arg
            print "Playback file: {}".format(filename)

    if filename == "":
        print "No playback file specified"
        sys.exit(1)

    if configfile == "":
        if os.path.isfile("~/.organ.conf"):
            configfile = "~/.organ.conf"
    if configfile == "":
        if os.path.isfile("/etc/organ.conf"):
            configfile = "/etc/organ.conf"
    if configfile == "":
        if os.path.isfile(sys.path[0] + "/organ.conf"):
            configfile = sys.path[0] + "/organ.conf"

    # Read config file
    try:
        if VERBOSE:
            print "Using config file: {}".format(configfile)
        config = ConfigParser.SafeConfigParser()
        config.read(configfile)
        mqttbroker = config.get("Global", "mqttbroker")
        mqttport = config.getint("Global", "mqttport")

    except ConfigParser.Error as e:
        print "Error parsing the configuration file"
        print e.message
        sys.exit(2)

    mqttclient = mqtt.Client("Playback")
    connect_to_mqtt(mqttbroker, mqttport)

    with open(filename, 'r') as f:
        playback = f.readlines()
    playback = [p.strip('\n') for p in playback]

    STARTTIME = time.time()

    try:
        for p in playback:
            if len(p) > 0 and p[0] != "#":
                pieces = p.split(':')
                if len(pieces) == 3:
                    playtime = pieces[0]
                    topic = pieces[1]
                    message = pieces[2]
                    timetowait = float(playtime) + STARTTIME - time.time()
                    if timetowait > 0:
                        time.sleep(timetowait)
                    mqttclient.publish(topic, message)
                    if DEBUG:
                        print "PLAY: ", pieces

    except KeyboardInterrupt:
            cont = False

    if VERBOSE:
        print "#Cleaning up"
        mqttclient.disconnect()
        mqttclient.loop_stop()
