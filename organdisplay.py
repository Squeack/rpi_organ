#!/usr/bin/python

from IOPi import IOPi
import time
import sys
import os.path
import getopt
import ConfigParser
import paho.mqtt.client as mqtt

def tobin(x, count=8):
    # type: (int, int) -> str
    return "".join(map(lambda y: str((x >> y) & 1), range(count - 1, -1, -1)))


class OrganDisplay:
    def __init__(self, configfile, verbose_flag, debug_flag):
        self.verbose = verbose_flag
        self.debug = debug_flag
        self.this_keyboard = config.getint("Local", "thiskeyboard")
        self.localsection = "Console" + str(self.this_keyboard)
        self.sbuses = []
        self.stopaddr = []
        self.numstopio = 0
        self.stoprport = 0
        self.stopwport = 0
        self.stopstate = []
        self.config = ConfigParser.SafeConfigParser()
        self.read_config(configfile)
        self.hardware_initialise()

    def read_config(self, configfile):
        self.config.read(configfile)
        alist = self.config.get(self.localsection, "iostopaddr")
        self.stopaddr = map(int, alist.split(","))
        self.numstopio = len(self.stopaddr)
        self.stopwport = self.config.getint(self.localsection, "stopwport")
        self.stoprport = self.config.getint(self.localsection, "stoprport")
        self.stopstate = [0L] * (self.numstopio * 8)

    def hardware_initialise_stops(self, bus, Wport, Rport):
        bus.set_port_direction(Wport, 0x00)
        bus.set_port_pullups(Wport, 0x00)
        bus.invert_port(Wport, 0x00)
        bus.write_port(Wport, 0x00)
        bus.set_port_direction(Rport, 0xFF)
        bus.set_port_pullups(Rport, 0xFF)
        bus.invert_port(Rport, 0xFF)
        if self.debug:
            bus.print_bus_status()

    def hardware_initialise(self):
        # Initialise hardware
        for n in range(0, self.numstopio):
            self.sbuses.append(IOPi(self.stopaddr[n]))
        for n in range(0, self.numstopio):
            self.hardware_initialise_stops(self.sbuses[n], self.stopwport, self.stoprport)

    def hardware_finalise_bus(self, bus):
        bus.write_port(0, 0x00)
        bus.write_port(1, 0x00)
        bus.set_port_direction(0, 0xFF)
        bus.set_port_pullups(0, 0x00)
        bus.invert_port(0, 0x00)
        bus.set_port_direction(1, 0xFF)
        bus.set_port_pullups(1, 0x00)
        bus.invert_port(1, 0x00)
        if self.debug:
            bus.print_bus_status()

    def hardware_finalise(self):
        if self.verbose:
            print "Reset hardware interfaces"
        for n in range(0, self.numstopio):
            self.hardware_finalise_bus(self.sbuses[n])

    def showLEDs(self):
        for n in range(0, self.numstopio):
            leds = 0
            for i in range(0, 8):
                sn = n * 8 + i
                if self.stopstate[sn] > 0:
                    leds = leds + (1 << (7 - i))
            if self.debug:
                print "Setting LED bank {} to {}".format(n, tobin(leds, 8))
            self.sbuses[n].write_port(self.stopwport, leds)

    def stop_on(self,s):
        self.stopstate[s] = 1
        self.showLEDs()

    def stop_off(self,s):
        self.stopstate[s] = 0
        self.showLEDs()

    def toggle_step(self,s):
        self.stopstate[s] = 1 - self.stopstate[s]
        self.showLEDs()

if __name__ == "__main__":
    DEBUG = False
    VERBOSE = False
    configfile = ""

    # noinspection PyUnusedLocal
    def on_mqtt_connect(client, userdata, flags, rc):
        if rc == 0:
            global mqttconnected
            if VERBOSE:
                print("Connected to MQTT broker")
            mqttconnected = True
        else:
            print("MQTT connection failed")
            sys.exit(3)


    # noinspection PyUnusedLocal
    def on_mqtt_message(client, userdata, message):
        global totaltime
        global numevents
        data = message.payload
        starttime = time.time()
        if DEBUG:
            print "%6.3f: " % starttime, message.payload
        pieces = data.split()
        while len(pieces) > 0:
            cmd = pieces[0]
            del pieces[0]
            # Note message
            if cmd == "N":
                del pieces[0]
                del pieces[0]
                del pieces[0]
            # Stop message
            if cmd == "S":
                n = int(pieces[0])
                a = int(pieces[1])
                if a == 0:
                    dorgan.stop_off(n)
                if a == 1:
                    dorgan.stop_on(n)
                if a == 2:
                    dorgan.toggle_step(n)
                del pieces[0]
                del pieces[0]
            # Mode message
            if cmd == "M":
                del pieces[0]

    # Check command line startup options
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hdvc:", ["help", "debug", "verbose", "config="])
    except getopt.GetoptError:
        sys.exit(1)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print "Options are -d [--debug], -v [--verbose], -c [--config=]<configfile>"
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
        num_keyboards = config.getint("Global", "numkeyboards")
        this_keyboard = config.getint("Local", "thiskeyboard")
        localsection = "Console" + str(this_keyboard)
        mqttbroker = config.get("Global", "mqttbroker")
        mqttport = config.getint("Global", "mqttport")
        topic = config.get(localsection, "topic")
    except ConfigParser.Error as e:
        print "Error parsing the configuration file"
        print e.message
        sys.exit(2)

    dorgan = OrganDisplay(configfile, VERBOSE, DEBUG)

    if VERBOSE:
        print "Subscribing to {} on MQTT broker at {}:{}".format(topic, mqttbroker, mqttport)
    mqttclient = mqtt.Client("Display" + localsection)
    mqttclient.on_connect = on_mqtt_connect
    mqttclient.on_message = on_mqtt_message
    mqttconnected = False
    mqttclient.connect(mqttbroker, mqttport, 30)
    mqttclient.loop_start()
    while mqttconnected is not True:
        time.sleep(0.1)

    mqttclient.subscribe(topic)

    if VERBOSE:
        print "Listening for published data"

    cont = True
    totaltime = 0.0
    numevents = 0
    while cont:
        try:
            # Incoming messages are handled by the mqtt callback
            time.sleep(1)

        except KeyboardInterrupt:
            cont = False

    if VERBOSE:
        print "Cleaning up"
        dorgan.hardware_finalise()
        mqttclient.disconnect()
        mqttclient.loop_stop()
