#!/usr/bin/python

"""
Copyright (c) 2018 Ian Shatwell

The above copyright notice and the LICENSE file shall be included with
all distributions of this software
"""

import sys
import signal
import time
import os
import psutil
import RPi.GPIO as GPIO


def signal_handler(signal, frame):
    GPIO.cleanup()
    sys.exit(0)


CPUWARNING = 80
PINSHUTDOWN = 17
PINHIGHCPU = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(PINSHUTDOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PINHIGHCPU, GPIO.OUT)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

cpuload = max(psutil.cpu_percent(interval=None, percpu=True))
countdown = 13
while True:
    # Check cpu usage
    cpuload = max(psutil.cpu_percent(interval=None, percpu=True))
    if cpuload > CPUWARNING:
        GPIO.output(PINHIGHCPU, 1)
    else:
        GPIO.output(PINHIGHCPU, 0)

    # Look for shutdown signal
    # Active low
    if GPIO.input(PINSHUTDOWN):
        countdown = 13
    else:
        countdown = countdown - 1
        if countdown == 0:
            print "BOOM!"
        else:
            print "Shutdown in {}".format(countdown)
    if countdown == 0:
        print "Shutdown command triggered"
        os.system("sync")
        time.sleep(3)
        os.system("sync")
        os.system("sudo shutdown -P now")
    time.sleep(0.25)
