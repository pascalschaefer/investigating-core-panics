"""
 Copyright © 2019 TimeTool AG. All rights reserved.
"""
import config
import pycom
import _thread
import time
import os
import machine
from network import WLAN

class EventSender:
    def __init__(self, options, logger, eventLog, led, lora):
        self.options = options
        self.logger = logger
        self.eventLog = eventLog
        self.led = led
        self.lora = lora
        self.isBlocked = False
        self.enabled = True
        self.testCounter = 0
        self.lock = _thread.allocate_lock()
        self._publisherThread = None
        self.lastSendEvent = time.time()

    # logging
    def log(self, *text):
        self.logger.log("EventSender", *text)

    def updateLastSendTime(self):
        self.lastSendEvent = time.time()

    def start(self):
        self.startPublisher()
        self.log("EventSender started")


    # starts the TX sender thread
    def startPublisher(self):
        if self._publisherThread == None:
            _thread.stack_size(64536)
            self._publisherThread = _thread.start_new_thread(self.sendPendingEvents, ())
            _thread.stack_size(0)

    # sends the eventlog entries that have not yet been transmitted
    def sendPendingEvents(self):
        while True:
            sleeptime = self.options['send_interval'] * (1 + config.LORA_RANDOMIZE_SLEEP * (os.urandom(1)[0] / 256))
            time.sleep(sleeptime)

            # update in order to detect time
            self.lastSendEvent = time.time()
            if self.enabled:
                # get next event to be sent
                hasEvents = self.eventLog.hasEvents()
                self.log("pending events:", hasEvents)
                if hasEvents:
                    event = self.eventLog.peekNextEvent()
                    if event == None:
                        self.led.ok()
                        self.log("ERROR: Unable to peek next event")
                    else:
                        eventId = event['ID']
                        command = event['Command']
                        self.log("Publishing event #", eventId, " with CMD", command)
                        pos = self.eventLog.ringBuffer.read_position
                        try:
                            if self.onPublish(event):
                                if pos == self.eventLog.ringBuffer.read_position:
                                    if self.eventLog.pullNextEvent() == None:
                                        self.log("ERROR: Unable to PULL next event in order to mark it as being sent")
                        except Exception as e:
                            self.log("ERROR", "Unable to publish event", e.args[0], e)
                    
        
    def onPublish(self, e):
        self.log("Handling event #", e['ID'], " with CMD", e['Command'])
        isHandled = False
        try:
            if self.lora.hasJoined():
                isHandled = self.lora.sendEvent(e)
            else:
                self.log("Unsupported uplink:", self.options['uplink'])
        except Exception as e:
            self.log("ERROR", "Unable to send event via", self.options['uplink'], e.args[0], e)

        # Flash the LED
        if isHandled:
            color = self.led.ok()
            time.sleep(0.05)
            self.led.setColor(color)
        else:
            color = self.led.error()
            time.sleep(0.05)
            self.led.setColor(color)

        return isHandled
