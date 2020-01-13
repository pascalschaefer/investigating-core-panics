import config
import pycom
import _thread

class Logger:
    def __init__(self):
        self.lock = _thread.allocate_lock()
        self.log("Logger started")

    # display starting/booting condition
    def _append(self, level, topic, *text):
        with self.lock:
            print(level + " [" + topic + "]", *text)

    # log text
    def log(self, topic, *text):
        self._append("TRACE", topic, *text)

    # log an error
    def error(self, topic, *text):
        self._append("ERROR", topic, *text)
