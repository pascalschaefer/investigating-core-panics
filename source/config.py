
# Software Version ---------------------------------------------
RELEASE_INFO = "TimeToolWK HW:WK19 FW:6 D:17.12.2019"
HW_VERSION = 0                                  # max 15
FW_VERSION = 6                                  # max 15


# Hardware Flags -----------------------------------------------
# Mainboard
HW_BOARD_PYSCAN1    = 0                         # PyScan board
HW_BOARD_EXPANSION3 = 1                         # Expansion Board 3.0
HW_BOARD            = HW_BOARD_EXPANSION3

# Power Management Settings ---------------------------------------------
UI_LED_OFF_WHEN_RUNNING = True                  # is the LED off by default?

# WATCHDOG ---------------------------------------------------------------
WDT_MAIN_TIMEOUT = 60000                        # main loop watchdog. 0 to disable WDT


# LORA Settings ---------------------------------------------------------
LORA_SLEEPTIME = 15                             # number of seconds to sleep between lora transmissions
LORA_RANDOMIZE_SLEEP = 0.2                      # randomize LORA_SLEEPTIME by 20%
LORA_SLEEPTIME_WHEN_NOT_CONNECTED = 20          # number of seconds to sleep when not otaa joined
LORA_USE_ABP = False                            # by default use OTAA
LORA_SEND_STATUS_INTERVAL = 3120                # send at least one packet every hour - should be alittle different than timesync

# RFID Settings ---------------------------------------------------------
RFID_SCAN_INTERVAL = 0.2                        # tag scan interval (200ms default)
RFID_LOG_UART = False                           # True to log UART communication
RFID_PAUSE_SCANNING_BUFFER_LEVEL = 90           # pause scanning when event buffer level is abofe 95%
RFID_WARN_LED_BUFFER_LEVEL = 80                 # LED orange when buffer level above 80%

# Logging Settings ---------------------------------------------------------
EVENT_LOG_PATH = '/flash/data/events.bin'
EVENT_LOG_BLOCKSIZE = 18                        # size (bytes) of one event log block (7 bytes header: ID + CMD + TS)
EVENT_LOG_MAX_EVENTS = 1000                     # number of events in log ringbuffer
EVENT_LOG_MAX_EVENT_ID = 0xFFFE                 # max value for Event ID until it rolls over
