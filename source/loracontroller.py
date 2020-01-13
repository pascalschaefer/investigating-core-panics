"""
 Copyright © 2019 TimeTool AG. All rights reserved.
"""
from network import LoRa
import pycom
import socket
import ubinascii
import binascii
import _thread
import time
import utime
import machine
import os
import config
import eventlog
import gc
from eventlog import EventLog

class LoraController:
    def __init__(self, options, logger, eventLog, ledController):
        self.options = options
        self.logger = logger
        self.eventLog = eventLog
        self.led = ledController

        self.lora = LoRa(mode=LoRa.LORA, power_mode=LoRa.SLEEP)
        self.tx_runner = None           # thread which sends events over lora
        self.lastJoin = 0               # when did we join the lora network
        self.isJoinLogged = False       # did we log the initial LORA join
        self.lastEventId = 0            # last sent event id
        self.sendLock = _thread.allocate_lock()
        self.socketLock = _thread.allocate_lock()
        self.isAckingCounter = 0
        self.noDownlinkCounter = 0
        self.lastUplinkTime = 0
        self.isAcking = False

    # logging
    def log(self, *text):
        self.logger.log("LORA", *text)

    # start lora connectivity
    def start(self):
        # setup lorawan
        self.lora = LoRa(mode=LoRa.LORAWAN, region=LoRa.EU868, device_class=LoRa.CLASS_A, tx_retries=3, adr=True, sf=12)
        self.lora.nvram_restore()

        self.lora.callback(trigger=(LoRa.RX_PACKET_EVENT | LoRa.TX_PACKET_EVENT | LoRa.TX_FAILED_EVENT), handler=self.lora_callback)
        self.log('Lora DevEUI is', self.getDeviceEUI())
        self.log('Lora AppEUI is', self.options['lora_app_eui'])

        if len(self.options['lora_app_eui']) != 16:
            self.log("ERROR", "Setting 'lora_app_eui' is invalid:", self.options['lora_app_eui'])
            return

        # issue join
        if self.options['lora_mode'] == "abp":
            self.join()
        elif self.lora.has_joined():
            self.log("Lora network is already joined, re-joining anyway")
        else:
            self.join()

    def lora_callback(self, lora):
        events = lora.events()
        if events & LoRa.TX_FAILED_EVENT:
            self.log('Lora TX FAILED')

    # determines the LORA MAC address (string)
    def getDeviceEUI(self):
        return ubinascii.hexlify(self.lora.mac()).decode('ascii').upper()


    # joins the lora network via OTAA
    def joinOTAA(self):
        app_eui = ubinascii.unhexlify(self.options['lora_app_eui'])
        app_key = ubinascii.unhexlify(self.options['lora_app_key'])

        self.lora.join(activation=LoRa.OTAA, auth=(app_eui, app_key), timeout=0)
        self.log("Joining via OTAA")
        self.lastJoin = time.time()

    # joins the lora network via ABP
    def joinABP(self):
        net_key = ubinascii.unhexlify(self.options['lora_net_key'])
        app_key = ubinascii.unhexlify(self.options['lora_app_key'])
        # note: TTN seems to want the reverse bytes of this address
        device_address = ubinascii.unhexlify(self.options['lora_dev_adr'])
        
        self.lora.join(activation=LoRa.ABP, auth=(device_address, net_key, app_key))
        self.log("Joining via ABP with device address", device_address)
        self.lastJoin = time.time()

    # joins the lora network via ABP or OTAA
    def join(self):
        if self.options['lora_mode'] == "abp":
            self.joinABP()
        else:
            self.joinOTAA()

    def hasJoined(self):
        return self.lora.has_joined()

    def stats(self):
        return self.lora.stats()

    def makePayload(self, event):
        payload = None
        command = event['Command']
        idbytes = event['ID'].to_bytes(2, 'little')
        event_ts = event['Time']
        try:
            if command == eventlog.CMD_TAG_DETECTED:
                # Tag with 4-Byte UID detected
                # <0x01> <Event ID 0..1> <Timestamp 0..3> <UID 0..3/6/9> 
                timeBytes = event_ts.to_bytes(4, 'little')
                uid = event['Data'][0:10]

                # remove trailing 0x00
                uid_size = 10
                for i in range(uid_size-1, 3, -1):
                    if uid[i] != 0x00:
                        break
                    uid_size = uid_size - 1
                uid = uid[:uid_size]

                payload = bytes([0x01]) + idbytes + timeBytes + uid
                uidText = ubinascii.hexlify(uid).decode()
                self.log("CMD 0x01 [NFC_DETECTED] SEQ#", event['ID'], ". uid =", uidText, ", ts =", event_ts)   

            if command == eventlog.CMD_TIME_REQUEST2:
                # ask backend for current time (new)
                # <0x04> <ID 0..1> <Our Time 0..3>
                mytime = time.time().to_bytes(4, 'little')
                payload = bytes([command]) + idbytes + mytime
                self.log("CMD 0x04 [TIME_REQUEST] ID#", event['ID'], ". our_time =", time.time(), utime.gmtime(time.time()) )

            if command == eventlog.CMD_TIME_CHANGED:
                # <0x05> <Event ID 0..1> <Our Time 0..3> <Old Time 0..3>
                mytime = event_ts.to_bytes(4, 'little')
                oldTime = event['Data'][0:4]
                payload = bytes([eventlog.CMD_TIME_CHANGED]) + idbytes + mytime + oldTime
                self.log("CMD 0x05 [TIME_CHANGED] SEQ#", event['ID'], ". our_time =", event_ts, utime.gmtime(event_ts), ", old_time =", oldTime)

        except Exception as e:
            self.log("ERROR: Unable to prepare LORA payload:", e.args[0], e)
        return payload

    # attempts to send the given event
    def sendEvent(self, event):
        with self.sendLock:
            eventId = event['ID']
            command = event['Command']
            self.log("Preparing to send CMD =", command, ", SEQ_NO =", eventId)
            if self.lastEventId > 0 and eventId > self.lastEventId + 1:
                self.log("ERROR", "Event IDs are not in sequence - last:", self.lastEventId, ", current:", eventId)
            self.lastEventId = eventId
            # prepare lora payload for supported event log entries
            payload = self.makePayload(event)
            if payload == None:
                self.log("WARN: Event payload is None and therefore ignored for lora transmission")
                return True
            # send payload
            return self.sendAndHandleResponse(payload)


    # sends the payload and handles the optional response
    def sendAndHandleResponse(self, payload):
        if not self.hasJoined():
            self.log("ERROR", "Unable to send LORA payload because not joined")
            return False

        # send
        responseData = self.sendPayload(payload)
        if responseData == False:
            self.noDownlinkCounter = self.noDownlinkCounter + 1
            return False

        # handle response
        if responseData != None and len(responseData) > 0:
            try:
                return True
            except Exception as e:
                self.log("ERROR: Unable to handle LORA payload: ", e.args[0], e)
                self.noDownlinkCounter = self.noDownlinkCounter + 1
        else:
            self.noDownlinkCounter = self.noDownlinkCounter + 1
        # the message has been sent
        return True

    def sendTimeRequest(self, clockSyncEvent, clockSyncRequests):
        clockSyncEvent['Command'] = eventlog.CMD_TIME_REQUEST2
        payload = self.makePayload(clockSyncEvent)
        try:
            with self.sendLock:
                # send lora uplink
                responseData = self.sendPayload(payload, False)
                if responseData == False:
                    return None

        except Exception as e:
            self.log("ERROR", "Unable to sync clock via LORA:", e.args[0], e)
        return None


    # send the specified payload
    def sendPayload(self, data, updateTime = True):
        try:
            with self.socketLock:
                self.log("> sending", len(data), "bytes:", binascii.hexlify(data))
                responseData = None
                # create a LoRa socket
                s = socket.socket(socket.AF_LORA, socket.SOCK_RAW)
                s.setblocking(False)
                try:
                    """free_memory = gc.mem_free()
                    allocated_memory = gc.mem_alloc()
                    print("Free Memory: " + str(free_memory) + " -- Allocated Memory : " + str(allocated_memory))"""
                    s.send(data)
                    time.sleep(5)
                    responseData = s.recv(64)
                except Exception as e:
                    self.log("ERROR", "LORA Socket Exception", e)
                s.close()
                if responseData != None:
                    responseLen = len(responseData)
                    if responseLen > 0:
                        self.log("< received", responseLen, "bytes:", binascii.hexlify(responseData))
                    else:
                        self.log("< no downlink")
                # log
                if updateTime == True:
                    self.lastUplinkTime = time.time()
                self.log(self.stats())
                time.sleep_ms(10)
                # save frame counters
                self.lora.nvram_save()
                time.sleep_ms(5)
                return responseData
        except Exception as e:
            self.log("ERROR", "Unable to send payload", e.args[0], e)
        return False
