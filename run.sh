#!/bin/sh

cd /home/tricorder/rpi_lcars-master/
cd app

if [-z $DISPLAY]; then
  xinit /usr/bin/python3 /home/tricorder/rpi_lcars-master/app/lcars.py
else
  /usr/bin/python3 /home/tricorder/rpi_lcars-master/app/lcars.py
fi
