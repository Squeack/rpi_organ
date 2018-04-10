#!/usr/bin/python

from IOPi import IOPi
import time
import sys
import ConfigParser
import paho.mqtt.client as mqtt


# Return an integer as a binary string of a given length
def tobin(x, count=8):
    # type: (int, int) -> str
    return "".join(map(lambda y: str((x >> y) & 1), range(count - 1, -1, -1)))


CYCLESNOOZE = 0.003

class OrganClient:
    def __init__(self, configfile, verbose_flag, debug_flag):
        self.verbose = verbose_flag
        self.debug = debug_flag
        self.thiskeyboard = -1
        self.numkeyboards = -1
        self.mqttbroker = ""
        self.mqttport = 0
        self.mqttclient = None
        self.localconfig = ""
        self.switchtype = "undefined"
        self.modes = []
        self.modeindex = 0
        self.noteaddr = []
        self.noterport = 0
        self.notewport = 0
        self.stopaddr = []
        self.numstopio = 0
        self.stoprport = 0
        self.stopwport = 0
        self.presetaddr = []
        self.numpresetio = 0
        self.noteoffset = 0
        self.numstops = 0
        self.numpresets = 0
        self.presetonlist = []
        self.presetofflist = []
        self.presetaction = []
        self.stoptrigger = []
        self.numcouplers = 0
        self.coupleroffset = 0
        self.couplertopics = []
        self.flakyswitches = False
        self.nbuses = []
        self.sbuses = []
        self.pbuses = []
        self.topic = []
        self.config = ConfigParser.SafeConfigParser()
        self.presetbin = 0
        self.notecheck = ""
        self.transposeamount = 0

        self.read_config(configfile)
        self.hardware_initialise()
        if self.switchtype == "matrix":
            self.notestate = "0" * 64
        else:
            self.notestate = "0" * 32
        self.oldnotestate = self.notestate
        self.stopstate = [0L] * (self.numstopio * 8)
        self.buttonstate = [False] * (self.numstopio * 8)
        self.stoptriggertime = [time.time()] * (self.numstopio * 8)
        if self.numpresets > 0:
            self.pbuttonstate = [False] * self.numpresets
            self.presettriggertime = [time.time()] * self.numpresets
        if self.switchtype == "matrix":
            self.keyboardstate = self.getmatrixkeyboardstate
        else:
            self.keyboardstate = self.getlinearkeyboardstate

    # Read configuration file
    def read_config(self, configfile):
        try:
            if self.verbose:
                print "Using config file: {}".format(configfile)
            self.config.read(configfile)
            self.numkeyboards = self.config.getint("Global", "numkeyboards")
            self.thiskeyboard = self.config.getint("Local", "thiskeyboard")
            self.localconfig = "Console" + str(self.thiskeyboard)
            self.mqttbroker = self.config.get("Global", "mqttbroker")
            self.mqttport = self.config.getint("Global", "mqttport")
            self.mqttclient = mqtt.Client("Client" + self.localconfig)
            self.mqttclient.connect(self.mqttbroker, self.mqttport, 30)
            self.mqttclient.loop_start()
            self.switchtype = self.config.get(self.localconfig, "switchtype")
            self.flakyswitches = self.config.has_option(self.localconfig, "flakyswitches")

            # What modes (instruments) are emulated ?
            alist = self.config.get(self.localconfig, "modes")
            self.modes = alist.split(",")
            self.modeindex = 0

            # Details about interfacing with the note hardware
            alist = self.config.get(self.localconfig, "ionoteaddr")
            self.noteaddr = map(int, alist.split(","))
            if self.switchtype != "matrix" and self.switchtype != "linear":
                print "Invalid switch type"
                sys.exit(3)
            if self.switchtype == "matrix":
                self.notewport = self.config.getint(self.localconfig, "notewport")
            self.noterport = self.config.getint(self.localconfig, "noterport")

            # Details about interfacing with the stop switch hardware
            alist = self.config.get(self.localconfig, "iostopaddr")
            self.stopaddr = map(int, alist.split(","))
            self.numstopio = len(self.stopaddr)
            self.stopwport = self.config.getint(self.localconfig, "stopwport")
            self.stoprport = self.config.getint(self.localconfig, "stoprport")

            # Details about interfacing with the preset switch hardware
            alist = self.config.get(self.localconfig, "iopresetaddr")
            if alist == "":
                self.presetaddr = []
            else:
                self.presetaddr = map(int, alist.split(","))
            self.numpresetio = len(self.presetaddr)

            self.noteoffset = self.config.getint(self.localconfig, "noteoffset")
            self.topic = [""] * self.numkeyboards
            for k in range(0, self.numkeyboards):
                self.topic[k] = self.config.get("Console" + str(k), "topic")
            self.change_mode(self.modeindex)
        except ConfigParser.Error as e:
            print "Error parsing the configuration file"
            print e.message
            sys.exit(1)

    # Publish an event for processing elsewhere (display, sound, recording, etc)
    def mqttpublish(self, message, topic):
        if message != "":
            self.mqttclient.publish(topic, message)
            if self.debug:
                print "INPUT: %6.3f" % time.time(), ": '{}' published to {}".format(message, topic)

    # Turn off all notes, not just limited to the keyboard range
    def zeronotes(self, topic):
        if self.verbose:
            print "Publishing note offs to {}".format(topic)
        for a in range(0, 8):
            data = ""
            for b in range(0, 16):
                note = a * 16 + b
                data += "N {} {} 0 ".format(self.thiskeyboard, note)
            self.mqttpublish(data, topic)

    # Turn off all stops
    def zerostops(self, topic):
        if self.verbose:
            print "Publishing stop offs to {}".format(topic)
        data = ""
        for i in range(0, self.numstops):
            data += "S {} 0 ".format(i)
        self.mqttpublish(data, topic)

    # Reset this keyboard and stop anything it might be triggering through couplers
    def resetservers(self):
        self.zeronotes(self.topic[self.thiskeyboard])
        self.zerostops(self.topic[self.thiskeyboard])
        if self.numcouplers > 0:
            for n in range(0, self.numcouplers):
                self.zeronotes(self.couplertopics[n])

    # Read the state of a switch matrix. e.g. manual keyboards
    def getmatrixkeyboardstate(self, buses):
        nstate = ""
        for n in range(0, len(buses)):
            for c in range(1, 9):
                # Write to each switch matrix column
                buses[n].write_port(self.notewport, 0xFF ^ (1 << (c - 1)))
                # Read rows
                p = buses[n].read_port(self.noterport)
                nstate += str(tobin(p))
        if self.flakyswitches:
            if len(self.notecheck) < len(nstate):
                oldnotecheck = nstate
            else:
                oldnotecheck = self.notecheck
            self.notecheck = nstate
            if self.debug:
                print "Comparing {} with {}".format(oldnotecheck, nstate)
            newnstate = ""
            for p in range(0,len(nstate)):
                if nstate[p] == "1" and oldnotecheck[p] == "1":
                    newnstate += "1"
                else:
                    if nstate[p] == "0" and oldnotecheck[p] == "1":
                        newnstate += "1"
                    else:
                        newnstate += "0"
            nstate = newnstate
        return nstate

    # Read the state of a linear switch set. e.g. pedalboard
    def getlinearkeyboardstate(self, buses):
        nstate = ""
        for n in range(0, len(buses)):
            # Read each bus
            p = buses[n].read_port(self.noterport)
            nstate += str(tobin(p))
            # Read the other port
            p = buses[n].read_port(1 - self.noterport)
            nstate += str(tobin(p))
        return nstate

    # Read the state of the preset switches
    def getpresetstate(self, buses):
        # Allow for mapping between the switch order and the wiring order at the IO port
        presetmap = [0, 15, 1, 14, 2, 13, 3, 12, 4, 11, 5, 10, 6, 9, 7, 8]
        pstate = list()
        if self.numpresetio > 0:
            for n in range(0, len(buses)):
                p = buses[n].read_port(0) + 256 * buses[n].read_port(1)
                s = tobin(p, 16)
                for b in range(0, 16):
                    pstate.append(s[presetmap[b]] == "1")
        return pstate

    def hardware_initialise_matrix(self, bus, wport, rport):
        bus.set_port_direction(wport, 0x00)
        bus.set_port_pullups(wport, 0x00)
        bus.invert_port(wport, 0x00)
        bus.write_port(wport, 0x00)
        bus.set_port_direction(rport, 0xFF)
        bus.set_port_pullups(rport, 0xFF)
        bus.invert_port(rport, 0xFF)
        if self.debug:
            bus.print_bus_status()

    def hardware_initialise_linear(self, bus):
        bus.set_port_direction(0, 0xFF)
        bus.set_port_pullups(0, 0xFF)
        bus.invert_port(0, 0xFF)
        bus.set_port_direction(1, 0xFF)
        bus.set_port_pullups(1, 0xFF)
        bus.invert_port(1, 0xFF)
        if self.debug:
            bus.print_bus_status()

    def hardware_initialise_stops(self, bus, wport, rport):
        bus.set_port_direction(wport, 0x00)
        bus.set_port_pullups(wport, 0x00)
        bus.invert_port(wport, 0x00)
        bus.write_port(wport, 0x00)
        bus.set_port_direction(rport, 0xFF)
        bus.set_port_pullups(rport, 0xFF)
        bus.invert_port(rport, 0xFF)
        if self.debug:
            bus.print_bus_status()

    def hardware_initialise_presets(self, bus):
        bus.set_port_direction(0, 0xFF)
        bus.set_port_pullups(0, 0xFF)
        bus.invert_port(0, 0xFF)
        bus.set_port_direction(1, 0xFF)
        bus.set_port_pullups(1, 0xFF)
        bus.invert_port(1, 0xFF)
        if self.debug:
            bus.print_bus_status()

    # Initialise various hardware interfaces
    def hardware_initialise(self):
        for n in range(0, len(self.noteaddr)):
            self.nbuses.append(IOPi(self.noteaddr[n]))
        self.notecheck = "0" * 8 * len(self.nbuses)
        for n in range(0, self.numstopio):
            self.sbuses.append(IOPi(self.stopaddr[n]))
        if self.numpresetio > 0:
            for n in range(0, self.numpresetio):
                self.pbuses.append(IOPi(self.presetaddr[n]))
        for n in range(0, len(self.noteaddr)):
            if self.switchtype == "matrix":
                self.hardware_initialise_matrix(self.nbuses[n], self.notewport, self.noterport)
            if self.switchtype == "linear":
                self.hardware_initialise_linear(self.nbuses[n])
        for n in range(0, self.numstopio):
            self.hardware_initialise_stops(self.sbuses[n], self.stopwport, self.stoprport)
        if self.numpresetio > 0:
            for n in range(0, self.numpresetio):
                self.hardware_initialise_presets(self.pbuses[n])

    # Set the hardware bus back to a normal state
    def hardware_finalise_bus(self, bus):
        # Zero outputs if in output mode
        bus.write_port(0, 0x00)
        bus.write_port(1, 0x00)
        # Return to input mode, no pull-ups, not inverted
        bus.set_port_direction(0, 0xFF)
        bus.set_port_pullups(0, 0x00)
        bus.invert_port(0, 0x00)
        bus.set_port_direction(1, 0xFF)
        bus.set_port_pullups(1, 0x00)
        bus.invert_port(1, 0x00)
        if self.debug:
            bus.print_bus_status()

    # Reset hardware and shut down MQTT publisher
    def hardware_finalise(self):
        if self.verbose:
            print "Reset hardware interfaces"
        self.mqttclient.loop_stop()
        self.mqttclient.disconnect()
        for n in range(0, len(self.noteaddr)):
            self.hardware_finalise_bus(self.nbuses[n])
        for n in range(0, self.numstopio):
            self.hardware_finalise_bus(self.sbuses[n])
        if self.numpresetio > 0:
            for n in range(0, self.numpresetio):
                self.hardware_finalise_bus(self.pbuses[n])

    # Load an instrument specific configuration
    def load_instrument_config(self, inst):
        if self.verbose:
            print "Loading {} configuration".format(inst)
        try:
            self.numstops = self.config.getint(self.localconfig + inst, "numstops")
            if self.numstops + self.numcouplers > 8 * self.numstopio:
                print "Too many stops ({}) and couplers ({}) for I/O chips ({}) to handle.".format(
                    self.numstops, self.numcouplers, self.numstopio)
                sys.exit(2)
            self.numpresets = 0
            self.presetonlist = []
            self.presetofflist = []
            if self.numpresetio > 0:
                self.numpresets = self.config.getint(self.localconfig + inst, "numpresets")
                if self.numpresets > 16 * self.numpresetio:
                    print "Too many presets ({}) for I/O chips ({}) to handle.".format(
                        self.numpresets, self.numpresetio)
                    sys.exit(3)
                self.presetaction = []
                for n in range(0, self.numpresets):
                    self.presetaction.append(self.config.get(self.localconfig + inst, "preset{}action".format(n)))
                    plist = self.config.get(self.localconfig + inst, "preset{}onlist".format(n))
                    self.presetonlist.append(map(int, plist.split(",")))
                    plist = self.config.get(self.localconfig + inst, "preset{}offlist".format(n))
                    self.presetofflist.append(map(int, plist.split(",")))
            clist = self.config.get(self.localconfig + inst, "couplers")
            couplers = map(int, clist.split(","))
            self.numcouplers = len(couplers)
            self.coupleroffset = 0
            if self.numcouplers > 0:
                self.coupleroffset = self.numstopio * 8 - self.numcouplers
                self.couplertopics = [""] * self.numcouplers
                for c in range(0, self.numcouplers):
                    self.couplertopics[c] = self.topic[couplers[c]]
        except ConfigParser.Error as e:
            print "Error parsing the instrument configuration file"
            print e.message
            sys.exit(1)

    # Change mode (instrument)
    def change_mode(self, m):
        self.modeindex = m % len(self.modes)
        self.load_instrument_config(self.modes[self.modeindex])
        data = "M {}".format(self.modeindex)
        for i in range(0, len(self.topic)):
            self.mqttpublish(data, self.topic[i])

    # Change transpose offset
    def transpose(self, t):
        self.transposeamount = t
        data = "T {} ".format(t)
        for i in range(0, len(self.topic)):
            self.mqttpublish(data, self.topic[i])


    # Handle a hardcoded special preset action
    # e.g. Changing mode
    def preset_special_action(self, actions):
        if self.verbose:
            print "Special action {}".format(actions)
        for i in actions:
            if i == 0:
                # Previous mode
                self.change_mode(self.modeindex - 1)
            if i == 1:
                # Next mode
                self.change_mode(self.modeindex + 1)
            if i == 2:
                # Transpose down
                self.transpose(self.transposeamount - 1)
            if i== 3:
                # Transpose up
                self.transpose(self.transposeamount + 1)

    # Report on the current configuration
    def print_status(self):
        print "This is keyboard {} of the range 0-{}".format(self.thiskeyboard, self.numkeyboards - 1)
        print "MQTT broker is {}".format(self.mqttbroker)
        print "Publishing on topic {}".format(self.topic[self.thiskeyboard])
        if self.switchtype == "matrix":
            print "Note switch matrix via IO chips {}".format(self.noteaddr)
        else:
            print "Linear note switches via IO chips {}".format(self.noteaddr)
        print "Stop switches via IO chip {}".format(self.stopaddr)
        if self.numcouplers > 0:
            for c in range(0, self.numcouplers):
                print "Coupler {} goes to {}".format(c + 1, self.couplertopics[c])
        else:
            print "No couplers"
        if self.numpresetio > 0:
            print "Preset switches via IO chips {}".format(self.presetaddr)
            print "{} presets".format(self.numpresets)
            for n in range(0, self.numpresets):
                print "Preset {} does '{}' action for stops {} on and stops {} off".format(
                    n, self.presetaction[n], self.presetonlist[n], self.presetofflist[n])
        else:
            print "No presets"
        print "Supported modes: {}".format(self.modes)
        if self.flakyswitches:
            print "Using switch glitch processing"

    def process_state(self):
        # Read note hardware
        oldnotestate = self.notestate
        time.sleep(CYCLESNOOZE)  # Helps synchronise chords and lowers cpu usage
        self.notestate = self.keyboardstate(self.nbuses)
        # Look for note changes
        changedebug = ""
        notechange = False
        notedata = ""
        for i in range(0, len(self.notestate)):
            if self.notestate[i] == oldnotestate[i]:
                changedebug += "."
            else:
                changedebug += self.notestate[i]
                notechange = True
                notedata += "N {} {} {} ".format(self.thiskeyboard, i + self.noteoffset, self.notestate[i])

        stopchange = False
        self.stoptrigger = [False] * (self.numstopio * 8)

        # Look at presets state
        # TODO: change stored stop state as preset if the preset has been held for a while
        if self.numpresets > 0:
            oldpbuttonstate = list(self.pbuttonstate)
            checktime = time.time()
            self.pbuttonstate = self.getpresetstate(self.pbuses)
            # Look for preset changes
            presetchange = False
            presettrigger = [False] * self.numpresets
            for i in range(0, self.numpresets):
                if self.pbuttonstate[i] and not oldpbuttonstate[i]:
                    if checktime > self.presettriggertime[i]:
                        if DEBUG:
                            print "INPUT: Preset {} pressed".format(i)
                        self.presettriggertime[i] = checktime + 0.1
                        presettrigger[i] = True
                        presetchange = True
            if presetchange:
                for i in range(0, self.numpresets):
                    if presettrigger[i]:
                        if self.presetaction[i] == "special":
                            self.preset_special_action(self.presetonlist[i])
                            # Only action a single special, as instrument config may have changed size of various arrays
                            # meaning loop indices may be out of range of array bounds
                            # nonlocal presetchange # Python3 specific
                            presetchange = False
                            # Reset LEDs
                            for n in range(0, self.numstopio * 8):
                                self.stopstate[n] = 0L
                            stopchange = True
                            break
                        if self.presetaction[i] == "change":
                            for n in self.presetonlist[i]:
                                if n >= 0:
                                    self.stoptrigger[n] = True
                                    self.stopstate[n] = 1L
                                    stopchange = True
                            for n in self.presetofflist[i]:
                                if n >= 0:
                                    self.stoptrigger[n] = True
                                    self.stopstate[n] = 0L
                                    stopchange = True

        # Look at stops state
        oldbuttonstate = list(self.buttonstate)
        checktime = time.time()
        oldp = self.presetbin
        self.presetbin = 0
        for n in range(0, len(self.sbuses)):
            self.presetbin += (256 ** n) * self.sbuses[n].read_port(self.stoprport)
        for i in range(0, self.numstopio * 8):
            self.buttonstate[i] = ((self.presetbin >> i) & 1) == 1
        # Look for stop changes
        for i in range(0, self.numstopio * 8):
            if (self.buttonstate[i] and not oldbuttonstate[i]):  # or (oldbuttonstate[i] and not buttonstate[i]):
                if checktime > self.stoptriggertime[i]:
                    if DEBUG:
                        print "INPUT: Trigger stop {} from state {} to {}".format(
                            i, tobin(oldp, 16), tobin(self.presetbin, 16))
                    # Allow 0.1s before button is allowed to act again to avoid bouncing
                    self.stoptriggertime[i] = checktime + 0.1
                    self.stoptrigger[i] = True
                    stopchange = True
        stopdata = ""
        # Couplers are always the last switches. There may be a gap between the stops and the couplers
        # coupleroffset = self.numstopio * 8 - self.numcouplers
        if stopchange:
            for n in range(0, self.numstopio):
                leds = 0
                for i in range(0, 8):
                    sn = n * 8 + i
                    if sn < self.numstops or sn >= self.coupleroffset:
                        if self.stoptrigger[sn] and self.buttonstate[sn]:
                            self.stopstate[sn] = 1L - self.stopstate[sn]
                            if DEBUG:
                                print "INPUT: Changing stop {} to {}".format(sn, self.stopstate[sn])
                        if self.stopstate[sn] > 0:
                            leds = leds + (1 << (7 - i))
                # if DEBUG:
                #     print "INPUT: Setting LED bank {} to {}".format(n, tobin(leds, 8))
                # self.sbuses[n].write_port(self.stopwport, leds)
            for i in range(0, self.numstopio * 8):
                if self.stoptrigger[i]:
                    stopdata = stopdata + "S {} {} ".format(i, self.stopstate[i])
            for i in range(0, self.numcouplers):
                if self.stoptrigger[i + self.coupleroffset]:
                    notechange = True

        if notechange or stopchange:
            if DEBUG:
                if notechange:
                    print "INPUT: ", changedebug
            self.mqttpublish(notedata + stopdata, self.topic[self.thiskeyboard])

        if notechange and self.numcouplers > 0:
            for n in range(0, self.numcouplers):
                if self.stopstate[n + self.coupleroffset] > 0:
                    extranotes = ""
                    if self.stoptrigger[n + self.coupleroffset]:
                        # Coupler has just been activated, so send already playing notes
                        notedata = ""
                        for i in range(0, len(self.notestate)):
                            if self.notestate[i] == "1":
                                extranotes += "N {} {} 1 ".format(self.thiskeyboard, i + self.noteoffset)
                    if (notedata + extranotes) != "":
                        self.mqttpublish(notedata + extranotes, self.couplertopics[n])
                else:
                    extranotes = ""
                    if self.stoptrigger[n + self.coupleroffset]:
                        # Coupler has just been deactivated, so stop already playing notes
                        for i in range(0, len(self.notestate)):
                            if self.notestate[i] == "1":
                                extranotes += "N {} {} 0 ".format(self.thiskeyboard, i + self.noteoffset)
                    if extranotes != "":
                        self.mqttpublish(extranotes, self.couplertopics[n])


if __name__ == "__main__":

    import os.path
    import getopt
    import signal

    DEBUG = False
    VERBOSE = False
    configfile = ""

    # noinspection PyUnusedLocal
    def signal_handler(signal, frame):
        global DEBUG
        global cont
        if DEBUG:
            print "Shutdown signal caught"
        cont = False


    # Check command line startup options
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hdvc:", ["help", "debug", "verbose", "config="])
    except getopt.GetoptError:
        sys.exit(2)

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
            print "Using config file: {}".format(configfile)

    if configfile == "":
        if os.path.isfile("~/.organ.conf"):
            configfile = "~/.organ.conf"
    if configfile == "":
        if os.path.isfile("/etc/organ.conf"):
            configfile = "/etc/organ.conf"
    if configfile == "":
        if os.path.isfile(sys.path[0] + "/organ.conf"):
            configfile = sys.path[0] + "/organ.conf"

    corgan = OrganClient(configfile, VERBOSE, DEBUG)

    # Display status
    if VERBOSE:
        corgan.print_status()

    cyclecount = 0

    # Set initial state on server
    corgan.resetservers()

    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    starttime = time.time()
    p = 0

    cont = True
    while cont:
        cyclecount += 1
        corgan.process_state()
    endtime = time.time()

    if VERBOSE:
        print "Cleaning up"
    # Reset servers
    corgan.resetservers()
    # Reset hardware interfaces
    corgan.hardware_finalise()

    print "Average cycle time = %4.2f" % (
                1000 * (endtime - starttime) / cyclecount), "ms, including a pause of %4.2f" % (
                1000 * CYCLESNOOZE), "ms"

    sys.exit(0)
