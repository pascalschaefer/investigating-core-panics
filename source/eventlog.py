"""
 Copyright © 2019 TimeTool AG. All rights reserved.
"""
import pycom
import time
import os
import binascii
import _thread
import config
from fileringbuffer import FileRingBuffer
import fileringbufferconstants

# Event Block Format
# <id 0..1> <cmd> <time 0..3> <data 0..n> <padding 0..n>
# ID        = 2 Bytes Event ID
# Time      = 4 Bytes RTC
# Data      = 0..n Bytes Data
# Padding   = 0..n ZEROes padding
# Max 16 bytes (EVENT_LOG_BLOCKSIZE)
# our events
CMD_TAG_DETECTED        = 0x02
CMD_TIME_REQUEST        = 0x03
CMD_TIME_REQUEST2       = 0x04
CMD_TIME_CHANGED        = 0x05

# represents a circular event log buffer
class EventLog:
    def __init__(self, logger, path):
        self.logger = logger
        self.eventIdLock = _thread.allocate_lock()
        self.enabled = True
        self.eventSender = None
        self.bufferLock = _thread.allocate_lock()
        self.ringBuffer = FileRingBuffer(path, config.EVENT_LOG_MAX_EVENTS * (config.EVENT_LOG_BLOCKSIZE + fileringbufferconstants._ITEM_SIZE_LEN))
        self.log("Initialized event log file", path, "with capacity for", config.EVENT_LOG_MAX_EVENTS, "events")
        self.log("> read position :", self.ringBuffer.read_position)
        self.log("> write position:", self.ringBuffer.write_position)

        # determine ID of last event written
        self.eventId = self.ringBuffer.getSequenceNumber()
        if self.eventId >= config.EVENT_LOG_MAX_EVENT_ID:
            self.eventId = 0
        self.lastAckEventID = self.ringBuffer.getAckNumber()
        if self.lastAckEventID >= config.EVENT_LOG_MAX_EVENT_ID:
            self.lastAckEventID = 0
        self.log("> eventId       :", self.eventId, "    lastAckEventID: ", self.lastAckEventID)

        if self.eventId == 0:
            # determine last event in event log
            self.eventId = -1
            lastEvent = self.peekLastEvent()
            if lastEvent == None:
                self.log("WARN: unable to determine last used event id, resetting at 0")
                self.lastAckEventID = 0
            else:
                self.eventId = lastEvent['ID']
                self.log("Restored eventID to", self.eventId)

        if self.lastAckEventID > self.eventId and self.eventId >= 0:
            self.log("Resetted lastAckEventID to", self.eventId, "from", self.lastAckEventID)
            self.lastAckEventID = self.eventId
    # logging
    def log(self, *text):
        self.logger.log("Eventlog", *text)

    def _advanceEventId(self):
        with self.eventIdLock:
            if self.eventId < config.EVENT_LOG_MAX_EVENT_ID:
                self.eventId = self.eventId + 1
            else:
                self.eventId = 0
            self.log("Advanced Event ID to", self.eventId)
            self.ringBuffer.storeSeqAck(self.eventId, self.lastAckEventID)
    
    def _formatEvent(self, cmd, data = None):
        id_raw = self.eventId.to_bytes(2, 'little')
        ts_raw = time.time().to_bytes(4, 'little')
        buffer = id_raw + bytes([cmd]) + ts_raw
        if data != None:
            buffer = buffer + data
        if (len(buffer) < config.EVENT_LOG_BLOCKSIZE):
            # pad with 0x00
            buffer = buffer + bytes(config.EVENT_LOG_BLOCKSIZE - len(buffer))
        elif (len(buffer) > config.EVENT_LOG_BLOCKSIZE):
            # trim entry
            buffer = buffer[:config.EVENT_LOG_BLOCKSIZE]
        return buffer

    # unpacks the binary event
    def _unpackEventPayload(self, block):
        if block != None and len(block) > 0:
            if len(block) == config.EVENT_LOG_BLOCKSIZE:
                eventId = int.from_bytes(block[0:2], 'little')
                eventTime = int.from_bytes(block[3:7], 'little')
                return {'ID':eventId, 'Command':block[2] ,'Time':eventTime, 'Data': block[7:len(block)]}
            else:
                self.log("ERROR: Invalid event block size. Expected:", config.EVENT_LOG_BLOCKSIZE, ", actual:", len(block))

        return None

    def addEvent(self, cmd, data = None):
        try:
            with self.bufferLock:
                self._advanceEventId()
                event_raw = self._formatEvent(cmd, data)
                self.ringBuffer.put(event_raw)
                self.log("Added Event", self.eventId, "to buffer, cmd =", cmd)
        except Exception as e:
            print("addEvent exception")

    # are there new events?
    def hasEvents(self):
        with self.bufferLock:
            return not self.ringBuffer.empty()

    def setEventSender(self, eventSender):
        self.eventSender = eventSender

    def peekNextEvent(self):
        with self.bufferLock:
            if not self.ringBuffer.empty():
                block = self.ringBuffer.peek()
                if block != None:
                    return self._unpackEventPayload(block)
            return None

    def pullNextEvent(self):
        with self.bufferLock:
            if not self.ringBuffer.empty():
                block = self.ringBuffer.get()
                if block != None:
                    return self._unpackEventPayload(block)
            return None

    # peeks the last event in the log
    def peekLastEvent(self):
        with self.bufferLock:
            block = self.ringBuffer.peekLast(config.EVENT_LOG_BLOCKSIZE)
            if block != None:
                return self._unpackEventPayload(block)
            return None
