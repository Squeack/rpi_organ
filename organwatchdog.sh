#!/bin/bash
while [ 1 ]
do
  if [ ! "$(/usr/bin/pgrep organsound)" ]
  then
    /usr/bin/logger "Starting organ sound server"
    /usr/bin/nohup /usr/bin/taskset 8 /usr/local/bin/organsound.py > /dev/null &
  fi
  if [ ! "$(/usr/bin/pgrep organdisplay)" ]
  then
    /usr/bin/logger "Starting organ display server"
    /usr/bin/nohup /usr/local/bin/organdisplay.py > /dev/null &
  fi
  if [ ! "$(/usr/bin/pgrep organinput)" ]
  then
    /usr/bin/logger "Starting organ input client"
    /usr/bin/nohup /usr/local/bin/organinput.py > /dev/null &
  fi
  if [ ! "$(/usr/bin/pgrep shutdownmonitor)" ]
  then
    /usr/bin/logger "Starting shutdown monitor"
    /usr/bin/nohup /usr/local/bin/shutdownmonitor.py > /dev/null &
  fi
  /bin/sleep 2
done
