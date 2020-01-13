# Constant indices within mmap buffers.
_POS_VALUE_LEN  = 8
_READ_POS_IDX   = 0
_WRITE_POS_IDX  = _POS_VALUE_LEN
_SEQ_ID_IDX     = _POS_VALUE_LEN * 2
_ACK_ID_IDX     = _POS_VALUE_LEN * 3
_HEADER_LEN     = _POS_VALUE_LEN * 4

# Item size constants.
_ITEM_SIZE_LEN = 4

# struct.[un]pack format string for length fields
_POS_VALUE_FORMAT = "q"
_ITEM_SIZE_FORMAT = "i"
