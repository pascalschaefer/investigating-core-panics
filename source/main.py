"""
 Copyright © 2019 TimeTool AG. All rights reserved.
"""
import time
import ubinascii
import binascii
import machine
import utime
import pycom
import gc
import os
from machine import WDT
from machine import Pin
from machine import Timer
from network import WLAN

import config
from logger import Logger
from loracontroller import LoraController
from ledcontroller import LedController
from clockController import ClockController
from eventsender import EventSender
import eventlog
from eventlog import EventLog

from fileringbufferconstants import (
  _HEADER_LEN, _ITEM_SIZE_FORMAT, _ITEM_SIZE_LEN, _POS_VALUE_FORMAT,
  _POS_VALUE_LEN, _READ_POS_IDX, _WRITE_POS_IDX, _SEQ_ID_IDX, _ACK_ID_IDX
)

# logging
logger = Logger()
def log(*text):
    logger.log("Main", *text)

log(os.uname())
log("Starting Wunderkiste App")
log(config.RELEASE_INFO)
device_id_text = binascii.hexlify(machine.unique_id()).upper()
log("MAC Address:", device_id_text)

# start watchdog
wdt = None
if (config.WDT_MAIN_TIMEOUT > 0):
    wdt = WDT(timeout=config.WDT_MAIN_TIMEOUT)

# init buzzer and LED
led = LedController()
led.starting()  

#TODO: change app_eui / app_key
options = {
    "device_id": "",
    "uplink": "lora",
    "send_interval": 5,
    "lora_mode": "otaa",
    "lora_app_eui": "F03D29AC71000001",
    "lora_app_key": "BBCC414FA8A0516AA3B87AA63ABF57FF",
    "lora_dev_adr": "",
    "lora_net_key": "",
    "clock_sync_retry_interval": 3,
    "clock_accuracy": 150,
    "clock_sync_interval": 25,
    "test_event_interval": 30,
}

# init event log
eventLog = EventLog(logger, config.EVENT_LOG_PATH)

#init lora controller
lora = LoraController(options, logger, eventLog, led)

# init event Sender Worker
eventSender = EventSender(options, logger, eventLog, led, lora)

# init event log
eventLog.setEventSender(eventSender)

# init lora and wait for join
if options['uplink'] == "lora":
    lora.start()
    lora.log("Waiting to join LORA network")
    while not lora.hasJoined():
        # Flash the LED red
        led.error()
        time.sleep(0.05)
        led.off()

        if (config.WDT_MAIN_TIMEOUT > 0):
            wdt.feed()
        time.sleep(2)
    lora.log("LORA is now joined")

# init RTC and clock
clockSyncRequests = {}
def onNetworkTimeRequest(clockEvent):
    global clockSyncRequests
    # blink led
    color = led.warn()
    time.sleep(0.05)
    led.setColor(color)

    clockEvent['Command'] = eventlog.CMD_TIME_REQUEST2
    clockSyncRequests[str(clockEvent['ID'])] = clockEvent
        
    returnVal = lora.sendTimeRequest(clockEvent, clockSyncRequests)
    if returnVal != None:
        clockSyncRequests = {}
    return returnVal

# setup time synchronization controller
clockService = ClockController(options, logger, eventLog, eventSender, eventLog, led, onNetworkTimeRequest)


test_uid = 1
is_interrupt_add_events_triggerd = False
is_interrupt_time_sync_triggered = False

# start time synchronization 
def timeSync(alarm):
    print("Timer.Alarm(): Time Sync started")
    global is_interrupt_time_sync_triggered
    is_interrupt_time_sync_triggered = True
    Timer.Alarm(timeSync, options['clock_sync_interval'], periodic=False)
Timer.Alarm(timeSync, options['clock_sync_interval'], periodic=False)

#adding 10 events
def interruptAddEvents():
    print("interruptAddEvents started")
    global test_uid   
    for x in range(0, 30):
        print("interruptAddEvents for " + str(x))
        uuid_pass = test_uid.to_bytes(4, 'little')
        test_uid += 1
        eventLog.addEvent(eventlog.CMD_TAG_DETECTED, uuid_pass)
        if (config.WDT_MAIN_TIMEOUT > 0):
            wdt.feed()

def corePanicTest(alarm):
    print("Timer.Alarm(): corePanicTest started")
    global is_interrupt_add_events_triggerd
    is_interrupt_add_events_triggerd = True
    Timer.Alarm(corePanicTest, options['test_event_interval'], periodic=False)
Timer.Alarm(corePanicTest, options['test_event_interval'], periodic=False)


# start event sender
eventSender.start()
interruptAddEvents()
#Main Loop
while True:

    # watchdog feed
    if (config.WDT_MAIN_TIMEOUT > 0):
        wdt.feed()
    
    # collect memory
    gc.collect()
    
    # sleep
    time.sleep(config.RFID_SCAN_INTERVAL)
    
    # Interrupt Based Code Execution via Flag for Adding Events
    # --> Here you need to wrap your head --> once in mail loop time sync is executed
    # even is triggered by alarm - main threat is still in clock sync
    """if is_interrupt_add_events_triggerd:
        is_interrupt_add_events_triggerd = False
        interruptAddEvents()"""
    
    # Interrupt Based Code Execution via Flag for Time Synchronization
    if is_interrupt_time_sync_triggered:
        is_interrupt_time_sync_triggered = False
        if clockService.isAlreadyRunning == False:
            clockService.acquireNetworkTimeThread(wdt)
        else:
            print("> clockService.acquireNetworkTimeThread would be started, but is already running")
