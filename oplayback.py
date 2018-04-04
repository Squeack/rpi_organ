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
            print("MQTT connection failed")
            sys.exit(3)


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

    if VERBOSE:
        print "Connecting to MQTT broker at {}:{}".format(mqttbroker, mqttport)
    mqttclient = mqtt.Client("Playback")
    mqttclient.on_connect = on_mqtt_connect
    mqttconnected = False
    mqttclient.connect(mqttbroker, mqttport, 30)
    mqttclient.loop_start()
    while mqttconnected is not True:
        time.sleep(0.1)

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