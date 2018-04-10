#!/usr/bin/python

import pyfs
import sys
import os.path
import time
import copy
import ConfigParser
import getopt
import paho.mqtt.client as mqtt

VOLUME = 127
NUM_KEYS = 128
FIRST_KEY = 35
LAST_KEY = 97


class OrganServer:
    def __init__(self, verbose_flag, debug_flag):
        self.verbose = verbose_flag
        self.debug = debug_flag
        if self.verbose:
            print "This is server {} in the range 0-{}".format(this_keyboard, num_keyboards - 1)
        self.channels = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15]  # Skip channel 9
        self.keys = [0] * NUM_KEYS
        self.allkeys = [[0] * NUM_KEYS for _ in range(num_keyboards)]
        self.num_stops = 1
        self.stops = [0] * self.num_stops
        self.notes = [[0] * NUM_KEYS for _ in range(self.num_stops)]
        self.oldnotes = [[0] * NUM_KEYS for _ in range(self.num_stops)]
        self.patches = [0]
        self.stopnames = [""]
        self.modeindex = 0
        self.sfid = 0
        mlist = config.get(localsection, "modes")
        self.modes = mlist.split(",")
        self.set_instrument(self.modeindex)
        self.transposeamount = 0

    def set_instrument(self, n):
        self.all_off()
        self.modeindex = n
        self.load_instrument(self.modes[self.modeindex])

    def load_instrument(self, inst):
        soundfont = config.get(localsection + inst, "soundfont")
        self.sfid = fs.sfload(soundfont)
        self.num_stops = config.getint(localsection + inst, "numstops")
        if self.num_stops > len(self.channels):
            print "More stops than channels available"
            sys.exit(4)
        self.patches = [0] * self.num_stops
        self.stopnames = [""] * self.num_stops
        if self.verbose:
            print "Using {} stops from {}".format(self.num_stops, soundfont)
        for s in range(0, self.num_stops):
            strs = str(s)
            self.patches[s] = config.getint(localsection + inst, "stop%s" % strs)
            self.stopnames[s] = config.get(localsection + inst, "stopname%s" % strs)
            fs.program_select(self.channels[s], self.sfid, 0, self.patches[s])
            if self.verbose:
                print "Configured stop {} to use patch {} ({})".format(s, self.patches[s], self.stopnames[s])
        self.stops = [0] * self.num_stops
        self.notes = [[0] * NUM_KEYS for _ in range(self.num_stops)]
        self.oldnotes = [[0] * NUM_KEYS for _ in range(self.num_stops)]

    def start_note(self, channel, note, velocity=127):
        if (note >= 0) and (note < NUM_KEYS):
            channel = self.channels[channel]
            if self.debug:
                print "SOUND: Start playing channel ", channel, ", note ", note
            fs.noteon(channel, note + self.transposeamount, velocity)

    def stop_note(self, channel, note):
        if (note >= 0) and (note < NUM_KEYS):
            channel = self.channels[channel]
            if self.debug:
                print "SOUND: Stop playing channel ", channel, ", note ", note
            fs.noteoff(channel, note + self.transposeamount)

    def find_changes(self):
        # Loop through each key
        for n in range(FIRST_KEY, LAST_KEY):
            self.keys[n] = 0
            # Look if this key is triggered locally or from a coupled keyboard
            for k in range(0, num_keyboards):
                if self.allkeys[k][n] > 0:
                    self.keys[n] = 1
                    break
            # Look if each stop is active
            for s in range(0, self.num_stops):
                if self.stops[s] > 0:
                    self.notes[s][n] = self.keys[n]
                else:
                    self.notes[s][n] = 0

        # Handle any changes from the previous state
        for s in range(0, self.num_stops):
            for n in range(FIRST_KEY, LAST_KEY):
                if self.notes[s][n] > self.oldnotes[s][n]:
                    self.start_note(s, n, VOLUME)
                if self.notes[s][n] < self.oldnotes[s][n]:
                    self.stop_note(s, n)
                self.oldnotes[s][n] = self.notes[s][n]

    def toggle_stop(self, stop):
        if self.stops[stop] == 0:
            self.stop_on(stop)
        else:
            self.stop_off(stop)

    def stop_on(self, stop):
        if (stop >= 0) and (stop < self.num_stops):
            if self.debug:
                print("SOUND: Stop on:{} ({}={})".format(stop, self.patches[stop], self.stopnames[stop]))
            self.stops[stop] = 1

    def stop_off(self, stop):
        if (stop >= 0) and (stop < self.num_stops):
            if self.debug:
                print("SOUND: Stop off:{} ({}={})".format(stop, self.patches[stop], self.stopnames[stop]))
            self.stops[stop] = 0

    def keyboard_key_down(self, keyboard, note):
        if self.debug:
            print "SOUND: Note " + str(note) + " down on keyboard " + str(keyboard)
        self.allkeys[keyboard][note] = 1

    def keyboard_key_up(self, keyboard, note):
        if self.debug:
            print "SOUND: Note " + str(note) + " up on keyboard " + str(keyboard)
        self.allkeys[keyboard][note] = 0

    def all_off(self):
        for k in range(0, num_keyboards):
            for n in range(FIRST_KEY, LAST_KEY):
                self.allkeys[k][n] = 0
        for s in range(0, len(self.stops)):
            self.stops[s] = 0

    def transpose(self, t):
        if self.debug:
            print "SOUND: Transpose by " + str(t)
        # Copy key state
        oldkeys = copy.deepcopy(self.allkeys)
        # Stop playing existing notes
        for k in range(0, num_keyboards):
            for n in range(FIRST_KEY, LAST_KEY):
                self.allkeys[k][n] = 0
        self.find_changes()
        # Copy key state back ready to restart notes
        self.allkeys = copy.deepcopy(oldkeys)
        self.transposeamount = t



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
            print "SOUND: %6.3f: " % starttime, message.payload
        pieces = data.split()
        while len(pieces) > 0:
            cmd = pieces[0]
            del pieces[0]
            # Note message
            if cmd == "N":
                k = int(pieces[0])
                n = int(pieces[1])
                v = int(pieces[2])
                if n >= 0 and n < 128:
                    if v > 0:
                        sorgan.keyboard_key_down(k, n)
                    if v == 0:
                        sorgan.keyboard_key_up(k, n)
                del pieces[0]
                del pieces[0]
                del pieces[0]
            # Stop message
            if cmd == "S":
                n = int(pieces[0])
                a = int(pieces[1])
                if a == 0:
                    sorgan.stop_off(n)
                if a == 1:
                    sorgan.stop_on(n)
                if a == 2:
                    sorgan.toggle_stop(n)
                del pieces[0]
                del pieces[0]
            # Mode message
            if cmd == "M":
                n = int(pieces[0])
                sorgan.all_off()
                sorgan.find_changes()
                sorgan.set_instrument(n)
                del pieces[0]
            if cmd == "T":
                t = int(pieces[0])
                sorgan.transpose(t)
                del pieces[0]
        # Handle the state changes
        sorgan.find_changes()
        endtime = time.time()
        totaltime = totaltime + (endtime - starttime)
        numevents = numevents + 1

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

    # Initialise synth connections
    fs = pyfs.Synth(0.2, 44100, 256, 16, 2, 64, 'no', 'no')
    fs.start(driver="alsa")
    # fs.start(driver = "jack")

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

    sorgan = OrganServer(VERBOSE, DEBUG)

    if VERBOSE:
        print "Subscribing to MQTT broker at {}:{}".format(mqttbroker, mqttport)
    mqttclient = mqtt.Client("Server" + localsection)
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
        mqttclient.disconnect()
        mqttclient.loop_stop()
        if numevents > 0:
            print "Average event process time = %4.2f" % (1000 * totaltime / numevents), "ms"
        else:
            print "No events received"
    fs.delete()
