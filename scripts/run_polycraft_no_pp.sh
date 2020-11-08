#!/bin/bash

# Run the Polycraft game server in its own screen.  The process that runs this script is not attached to the new screen.
# ./run_polycraft.sh <name for screen>

if [ -z "$1" ]; then
        echo usage: $0 world_name
        exit
fi

# First, issue the stop command to the world if it's already running
if [[ -n `screen -list | grep $1` ]] ; then
        screen -S $1 -X stuff "/say Hello everyone.  This server will restart in 10 seconds.\n" > /dev/null
        sleep 10s
        screen -S $1 -X stuff "/stop\n" > /dev/null
        sleep 10s
fi

# Then, change directory to where polycraft lives
cd /home/polycraft/$1

# Then, run polycraft in a screen.  Uncomment the correct command line to use either local or remote REST info
screen -d -m -S $1 java -jar -Xms4G -Xmx6G -XX:+UseConcMarkSweepGC -d64 -Dbest.default.directory=/mnt/PolycraftGame/round2main/ -Danalytics.enabled=true -DisBestServer=true -XX:+UseParNewGC -XX:+CMSIncrementalPacing -XX:ParallelGCThreads=4 -XX:+AggressiveOpts -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:$1.gc /home/polycraft/$1/polycraft-launcher.jar nogui