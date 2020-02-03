"""
 Copyright © 2019 TimeTool AG. All rights reserved.
"""
import config
import pycom
import machine
import time
import utime
import _thread
import eventlog
import config

class ClockController:
    def __init__(self, options, logger, eventlog, eventSender, eventLog, led, onNetworkTimeRequest = None):
        self.options = options
        self.logger = logger
        self.eventLog = eventlog
        self.eventSender = eventSender
        self.onNetworkTimeRequest = onNetworkTimeRequest
        self.enabled = False
        self.lastClockChange = 0
        self.rtc = machine.RTC()
        self.led = led
        self.blocked = False
        self.isAlreadyRunning = False

    def log(self, *text):
        self.logger.log("Clock", *text)

    def setTime(self, new_time, logEvent = True):
        now = time.time()
        self.log("Changing RTC from", now, "to", new_time)
        self.rtc.init((new_time))
        self.lastClockChange = now
        if logEvent:
            self.eventLog.addEvent(eventlog.CMD_TIME_CHANGED, now.to_bytes(4, 'little'))
        return True

    def acquireNetworkTimeThread(self, wdt):
        self.acquireNetworkTime(wdt)

    def acquireNetworkTime(self, wdt):
        self.log("Starting time sync")
        self.isAlreadyRunning = True
        isClockSynced = False
        clockSyncID = 0
        sleepDuration = self.options['clock_sync_retry_interval']
        sleepFactor = 1.3
        sleepMaxSeconds = 300
        if wdt != None:
            sleepMaxSeconds = (config.WDT_MAIN_TIMEOUT/1000) - 2
        while not isClockSynced:
            # watchdog feed
            if (config.WDT_MAIN_TIMEOUT > 0):
                wdt.feed()
            self.led.error()
            try:
                clockSyncID += 1
                if clockSyncID > 30:
                    clockSyncID = 0

                clockSyncEvent = {
                    'ID': clockSyncID, 
                    'Command': eventlog.CMD_TIME_REQUEST2,
                    'Time': time.time(), 
                    'Data': None
                }

                # get time
                oldTime = time.time()
                tuple_time = self.onNetworkTimeRequest(clockSyncEvent)  #tuple

                # handle response
                if tuple_time != None:
                    self.setTime(tuple_time, False)
                    timeDifference = time.time() - oldTime

                    # is clock synced?
                    if abs(timeDifference) < self.options['clock_accuracy']:
                        isClockSynced = True
                        self.isAlreadyRunning = False
                        self.log("Clock is now synced to ", utime.gmtime(time.time()), "with accuracy of", abs(timeDifference), "seconds")
            
            except Exception as e:
                self.log("ERROR", "Unable to synchronize clock:", e.args[0], e)
            
            if not isClockSynced:
                time.sleep(sleepDuration)    
                # sleep a little bit longer next time
                #sleepDuration = sleepDuration * sleepFactor
                #if sleepDuration > sleepMaxSeconds:
                 #   sleepDuration = sleepMaxSeconds

