import config
import pycom

class LedController:
    def __init__(self):
        self.color = 0x000000
        pycom.heartbeat(False)

    # display starting/booting condition
    def setColor(self, color):
        oldColor = self.color
        self.color = color
        pycom.rgbled(color)
        return oldColor


    # display starting/booting condition
    def starting(self):
        return self.setColor(0xFF0000)  # Red


    # display an error
    def error(self):
        return self.setColor(0xFF0000)  # Red


    # display a warning
    def warn(self):
        return self.setColor(0xFFA500)  # Orange


    # display a tag that was detected
    def tagDetected(self):
        return self.setColor(0x0000FF)  # Blue


    # everything ok
    def ok(self):
        return self.setColor(0x00FF00)  # Green

    # everything ok
    def off(self):
        return self.setColor(0x000000)  # off

    # color while scanning
    def scanning(self):
        if config.UI_LED_OFF_WHEN_RUNNING:
            return self.off()
        else:
            return self.ok()
