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

# Use local file for whitelist and private property data
#screen -d -m -S $1 java -jar -Xms1G -Xmx6000M -XX:+UseConcMarkSweepGC -d64 -Dportal.rest.url=file:///home/polycraft/$1/rest/ -Danalytics.enabled=true -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:$1.gc /home/polycraft/$1/polycraft-launcher-7.29.15.jar nogui

# Call REST service for whitelist and private property data
#screen -d -m -S $1 java -jar -Xms4G -Xmx6G -XX:+UseConcMarkSweepGC -d64 -Dportal.rest.url=http://10.0.0.7:9000/rest -Danalytics.enabled=true -XX:+UseParNewGC -XX:+CMSIncrementalPacing -XX:ParallelGCThreads=4 -XX:+AggressiveOpts -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:$1.gc /home/polycraft/$1/polycraft-launcher.jar nogui

# Call REST service for whitelist and private property data
screen -d -m -S $1 java -jar -Xms4G -Xmx6G -XX:+UseConcMarkSweepGC -d64 -Danalytics.enabled=true -Dbest.debug=true -DisBestServer=true =Dbest.default.directory=/mnt/PolycraftGame/testsR1/ -XX:+UseParNewGC -XX:+CMSIncrementalPacing -XX:ParallelGCThreads=4 -XX:+AggressiveOpts -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:$1.gc /home/polycraft/$1/polycraft-launcher.jar nogui
#screen -d -m -S $1 java -jar -Xms4G -Xmx6G -XX:+UseConcMarkSweepGC -d64 -Danalytics.enabled=true -Dbest.debug=true -DisBestServer=true =Dbest.default.directory=/mnt/PolycraftGame/testsR1/ -Dportal.rest.url=http://polycraft-beta.cloudapp.net/rest -XX:+UseParNewGC -XX:+CMSIncrementalPacing -XX:ParallelGCThreads=4 -XX:+AggressiveOpts -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:$1.gc /home/polycraft/$1/polycraft-launcher.jar nogui

#screen -d -m -S "oxygen" java -jar -Xms4G -Xmx6G -XX:+UseConcMarkSweepGC -d64 -Danalytics.enabled=true -Dbest.debug=true -DisBestServer=true =Dbest.default.directory=/mnt/PolycraftGame/testsR1/ -Dportal.rest.url=http://polycraft-beta.cloudapp.net/rest -XX:+UseParNewGC -XX:+CMSIncrementalPacing -XX:ParallelGCThreads=4 -XX:+AggressiveOpts -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:oxygen.gc /home/polycraft/oxygen/polycraft-launcher.jar nogui