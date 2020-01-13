from fileringbufferconstants import (
  _HEADER_LEN, _ITEM_SIZE_FORMAT, _ITEM_SIZE_LEN, _POS_VALUE_FORMAT,
  _POS_VALUE_LEN, _READ_POS_IDX, _WRITE_POS_IDX, _SEQ_ID_IDX, _ACK_ID_IDX
)
import os
import struct
import _thread
import pycom
import ubinascii
import binascii

class FileRingBuffer(object):
  """A file-based ring buffer.

  The underlying file buffer is prefixed with a header containing two
  64-bit integers representing the current read and write positions
  within the buffer. These positions are updated with each read and
  write in order to make buffer state fully reflected in the on-disk
  format.

  A single logical slot in the ring buffer is always left unallocated
  in order to ensure that the read and write positions are only ever
  equal when the buffer is empty [1].

  Because of these two conditions, the actual size of the underlying
  file, in terms of the arguments to `__init__`, is equal to

      8 + 8 + capacity + 1

  [1] http://en.wikipedia.org/wiki/Circular_buffer#Always_keep_one_slot_open
  """

  use_nvs = True

  def _get_stored_value(self, buffer_file, index):
    if self.use_nvs:
      try:
        value = pycom.nvs_get("wkb"+str(index))
        if value == None:
          return 0
        return value
      except Exception as e:
        print("> _get_stored_value: ", "failed:", e.args[0], e)
        return 0

    buffer_file.seek(index)
    value = struct.unpack(
      _POS_VALUE_FORMAT,
      buffer_file.read(_POS_VALUE_LEN)
    )[0]
    return value


  def _get_stored_read_position(self, buffer_file):
    """Return the read position that is recorded in the header of the
    underlying buffer. If the recorded read position is invalid, the
    initial read position is returned.

    Under normal operation, this will equal
    `self.read_position`. However when initializing a
    `FileRingBuffer` from a buffer file, the former read and write
    positions must be determined from the storage medium.
    """
    recorded_read_position = self._get_stored_value(buffer_file, _READ_POS_IDX)
    if recorded_read_position == 0:
      return _HEADER_LEN
    else:
      return recorded_read_position


  def _get_stored_write_position(self, buffer_file):
    """Return the write position that is recorded in the header of the
    underlying buffer. If the recorded write position is invalid, the
    initial write position is returned.

    Under normal operation, this will equal
    `self.read_position`. However when initializing a
    `FileRingBuffer` from a buffer file, the former read and write
    positions must be determined from the storage medium.
    """
    recorded_write_position = self._get_stored_value(buffer_file, _WRITE_POS_IDX)
    if recorded_write_position == 0:
      return _HEADER_LEN
    else:
      return recorded_write_position


  def _get_stored_sequence_number(self, buffer_file):
    return self._get_stored_value(buffer_file, _SEQ_ID_IDX)

  def _get_stored_ack_number(self, buffer_file):
    return self._get_stored_value(buffer_file, _ACK_ID_IDX)

  def _record_rw_positions(self, buffer_file):
    """Record the current read and write positions to the buffer
    header.
    """
    if self.use_nvs:
      try: 
        pycom.nvs_set("wkb"+str(_READ_POS_IDX), self.read_position)
        pycom.nvs_set("wkb"+str(_WRITE_POS_IDX), self.write_position)
      except Exception as e:
        print("> _record_rw_positions: ", "failed:", e.args[0], e)
      return
      

    packed_read_position = struct.pack(_POS_VALUE_FORMAT, self.read_position)
    packed_write_position = struct.pack(_POS_VALUE_FORMAT, self.write_position)
    buffer_file.seek(_READ_POS_IDX)
    buffer_file.write(packed_read_position)
    buffer_file.seek(_WRITE_POS_IDX)
    buffer_file.write(packed_write_position)


  def _record_seq_ack(self, buffer_file, seq, ack):
    if self.use_nvs:
      pycom.nvs_set("wkb"+str(_SEQ_ID_IDX), seq)
      pycom.nvs_set("wkb"+str(_ACK_ID_IDX), ack)
      return

    packed_seq_id = struct.pack(_POS_VALUE_FORMAT, seq)
    packed_ack_id = struct.pack(_POS_VALUE_FORMAT, ack)
    buffer_file.seek(_SEQ_ID_IDX)
    buffer_file.write(packed_seq_id)
    buffer_file.seek(_ACK_ID_IDX)
    buffer_file.write(packed_ack_id)

  def _get_stored_sequence_number(self, buffer_file):
    return self._get_stored_value(buffer_file, _SEQ_ID_IDX)

  def _get_stored_ack_number(self, buffer_file):
    return self._get_stored_value(buffer_file, _ACK_ID_IDX)


  def __init__(self, file_path, capacity):
    try:
      """
      Parameters
      ----------
      file_path : path to a file to use in the buffer
      capacity : total size, in bytes, of the data set stored in the buffer
      """
      self.file_path = file_path
      self.mode = "r+b"
      self.capacity = capacity
      self.buffer_size = _HEADER_LEN + capacity + 1
      self.iolock = _thread.allocate_lock()       # IO lock
      path = "/flash/data"
      
      try:
        os.stat(path)
      except:
        os.mkdir(path)

      try:
        os.stat(self.file_path)
      except:
        t = open(self.file_path, "w")
        t.close()

      with self.iolock:
        with open(self.file_path, self.mode) as buffer_file:
          dummy = True
        current_file_size = os.stat(file_path)[6]
        with open(self.file_path, self.mode) as buffer_file:
          # Open the file and ensure that its length is equal to `self.buffer_size`.
          #buffer_file.truncate(self.buffer_size)
          
          # expand file if size does not match desired buffer
          # TODO: if we ever change MAX_ITEMS in the field we'll lose data
          if current_file_size != self.buffer_size and (self.buffer_size - current_file_size) > 0:
            print("**** eventfile expanding buffer_size", self.buffer_size, "vs file_size",current_file_size)
            buffer_file.seek(current_file_size)
            buffer_file.write("\0" * (self.buffer_size - current_file_size))
            buffer_file.flush()
            self.read_position = _HEADER_LEN
            self.write_position = _HEADER_LEN
            self._record_seq_ack(buffer_file, 0, 0)
          else:
            # initialize the read and write positions.
            self.read_position = self._get_stored_read_position(buffer_file)
            self.write_position = self._get_stored_write_position(buffer_file)
          self._record_rw_positions(buffer_file)
    except Exception as e:
      print("> __init__: ", "failed:", e.args[0], e)

  def empty(self):
    """Return `True` if the buffer is empty, `False` otherwise."""
    return self.read_position == self.write_position

  def _advance_read_position(self, buffer_file):
    """Advances the reader position by one item."""
    buffer_file.seek(self.read_position)
    read_position_delta = struct.unpack(
      _ITEM_SIZE_FORMAT,
      buffer_file.read(_ITEM_SIZE_LEN)
    )[0]
    self.read_position += (_ITEM_SIZE_LEN + read_position_delta)


  def _reader_needs_advancing(self, n):
    """Given the precondition that there is at least `n` bytes between
    the write position and the end of the buffer, returns `True` if
    there is enough space between the write and read positions to
    allocate `n` bytes.
    """
    return self.read_position > self.write_position and (
      self.read_position - self.write_position < _ITEM_SIZE_LEN + n)


  def putString(self, item):
    """Put the bytes of the string `item` in the buffer."""
    assert type(item) is str, "items put into ring buffer must be strings"
    data = bytes(item)
    self.put(data)

  def simulateDestruction(self):
    try:
      with self.iolock:
        with open(self.file_path, self.mode) as buffer_file:
          buffer_file.seek(0)
          buffer_file.write('\0' * (self.buffer_size))
          buffer_file.flush()
    except Exception as e:
      print("> simulatedesctruction ", e.args[0], e)
      raise e

  def put(self, item):
    try: 
      """Put the bytes of the string `item` in the buffer."""
      assert type(item) is bytes, "items put into ring buffer must be bytes"
      with self.iolock:
        with open(self.file_path, self.mode) as buffer_file:
          item_len = len(item)
          assert _ITEM_SIZE_LEN + item_len <= self.capacity, "item size exceeds buffer capacity"
          # If there isn't enough space from the write position to the end
          # of the buffer, then wrap around.
          prev_write_position = self.write_position
          was_empty = self.empty()
          if self.write_position + _ITEM_SIZE_LEN + item_len + 1 > self.buffer_size:
            self.write_position = _HEADER_LEN
            if was_empty:
              # Buffer was empty, so reset read position to reflect emptiness.
              self.read_position = _HEADER_LEN
            elif self.read_position > prev_write_position:
              # In wrapping around, the write position lapped the read
              # position, so the latter must be advanced one past
              # _HEADER_LEN.
              self.read_position = _HEADER_LEN
              self._advance_read_position(buffer_file)
          # If the buffer wasn't empty and there isn't enough space between
          # the write and read positions to fit the item, then advance the
          # read position until it fits.
          while not was_empty and self._reader_needs_advancing(item_len):
            self._advance_read_position(buffer_file)
          
          # Now that enough writer headroom has been ensured, it is safe to
          # write the item.
          
          eventId = int.from_bytes(item[0:2], 'little')
          eventTime = int.from_bytes(item[3:7], 'little')
          event = {'ID':eventId, 'Command':item[2] ,'Time':eventTime, 'Data': item[7:len(item)]}
          
          buffer_file.seek(self.write_position)
          buffer_file.write(struct.pack(_ITEM_SIZE_FORMAT, item_len))
          buffer_file.write(item)
          
          if buffer_file.tell() >= self.buffer_size:
            self.write_position = _HEADER_LEN
            
          else:
            self.write_position = buffer_file.tell()
          
          self._record_rw_positions(buffer_file)
          buffer_file.flush()
    except Exception as e:
      print("> put: ", "failed:", e.args[0], e)

  def getString(self):
    """Remove and return the next string from the buffer."""
    data = self.get()
    return str(data)


  def get(self):
    """Remove and return the next item from the buffer."""
    with self.iolock:
      with open(self.file_path, self.mode) as buffer_file:
        # Read the current item.
        result = self._readItemAtPosition(buffer_file, self.read_position)

        # Update the read position.
        if buffer_file.tell() >= self.buffer_size - 1:
          self.read_position = _HEADER_LEN
          # 27.07.2019 - inifity loop sending events
          # when buffer is exactly filled and only as long it is.:
          # WRITE POS will point to END - Once last element is send, READ_POS will point to START by upper line
          # WRITE POS will be moved, once new element gets added
          # because WRITE_POS != READ_POS means not empty, events will be send again through
          if self.write_position >= self.buffer_size-1:
            self.write_position = _HEADER_LEN
        else:
          self.read_position = buffer_file.tell()

        self._record_rw_positions(buffer_file)
        buffer_file.flush()
        return result

  def printReadWritePos(self):
    print("Read Position: ", self.read_position)
    print("Write Position: ", self.write_position)

  def printSeqAck(self):
    print("Event ID: ", self.getSequenceNumber())
    print("Last Event ID ACKED: ", self.getAckNumber())

  def printFileRingBufferStatus(self):
    self.printReadWritePos()
    self.printSeqAck()

  def _readItemAtPosition(self, buffer_file, position, max_len = 100):
    """Reads the item at the specified position in the buffer. Not thread safe."""
    if position >= self.buffer_size - 1:
      return None

    try:
      buffer_file.seek(position)
      item_len = struct.unpack(
        _ITEM_SIZE_FORMAT,
        buffer_file.read(_ITEM_SIZE_LEN)
      )[0]
      if item_len <= 0:
        return None
      if item_len > max_len:
        item_len = max_len
      return buffer_file.read(item_len)
    except Exception as e:
      print("> readItemAtPosition", position, "of", self.buffer_size, "failed:", e.args[0], e)
      raise e

  # TODO: how to handle situation where self.empty() == false but next event can't be picked up?
  def peek(self):
    """Peek the next item in the buffer, e.g. the one at `read_position`, without removing it."""
    # 27.07.2019 - TODO: possible reason of the following mistical bug:
    # device was at last element 999 (e7)
    # boots + badging the same time
    # server got boot cmd. with event id 00 ??
    # badge event e8 was written but not send
    # furher badge events 1001, 1002 were send successfully but because of previous 00
    # not accepted
    if self.empty():
      return None

    with self.iolock:
      with open(self.file_path, "r+b") as buffer_file:
        # 27.07.2019 - if a device is stuck at the end
        # no events can be peeked anymore
        # should not longer happen because of fixing the advanceReadPositionFrom
        # but if a device is stucked after the update
        # this helps to let the device recover
        # if the READ_POS is moved, we need to check again whether it is empty
        # preventing from looping again through
        if self.read_position >= self.buffer_size-1:
          self.read_position = _HEADER_LEN
          if self.empty():
            return None
        return self._readItemAtPosition(buffer_file, self.read_position)


  def peekLast(self, blockSize):
    """Peek the last item written to the buffer, e.g. the item at `write_position - blockSite`."""
    pos = self.write_position - blockSize - _ITEM_SIZE_LEN
    if pos < _HEADER_LEN:
      # TODO: roll over
      pos = self.buffer_size - 1 - blockSize - _ITEM_SIZE_LEN
      #return None

    with self.iolock:
      with open(self.file_path, "r+b") as buffer_file:
        return self._readItemAtPosition(buffer_file, pos, blockSize)


  # TODO: use iterable / yield
  def iterate(self, callback):
    """Remove and return the next item from the buffer."""
    with self.iolock:
      with open(self.file_path, "r+b") as buffer_file:
        pos = _HEADER_LEN
        while pos < self.buffer_size - _ITEM_SIZE_LEN - 1:
            data = self._readItemAtPosition(buffer_file, pos)
            if data == None or len(data) == 0:
              return

            if not callback(data, pos):
              return

            pos = pos + _ITEM_SIZE_LEN + len(data)


  def setReadPosition(self, position):
    with self.iolock:
      self.read_position = position
      with open(self.file_path, self.mode) as buffer_file:
        self._record_rw_positions(buffer_file)
        buffer_file.flush()


  def advanceReadPositionFrom(self, position):
    with self.iolock:
      self.read_position = position
      with open(self.file_path, self.mode) as buffer_file:
        self._advance_read_position(buffer_file)
        # 25.07.2019 - Device gets stuck in eventLog.peekNext()
        # Cause: if a ACK moves the read pointer to the last element in the fileringbuffer
        # advanceReadPositionFrom doesn't check for END
        if self.read_position >= self.buffer_size - 1:
          self.read_position = _HEADER_LEN
        self._record_rw_positions(buffer_file)
        buffer_file.flush()


  def clear(self):
    """Remove all elements from the buffer."""
    with self.iolock:
      with open(self.file_path, self.mode) as buffer_file:
        buffer_file.seek(0)
        buffer_file.write("\0" * self.buffer_size)
        self.read_position = _HEADER_LEN
        self.write_position = _HEADER_LEN
        self._record_rw_positions(buffer_file)


  def storeSeqAck(self, seq, ack):
    try:
      with self.iolock:
        with open(self.file_path, self.mode) as buffer_file:
          self._record_seq_ack(buffer_file, seq, ack)
    except Exception as e:
      print("> storeSeqAck failed:", e.args[0], e)
      raise e

  def getSequenceNumber(self):
    with self.iolock:
      with open(self.file_path, self.mode) as buffer_file:
        return self._get_stored_sequence_number(buffer_file)


  def getAckNumber(self):
    with self.iolock:
      with open(self.file_path, self.mode) as buffer_file:
        return self._get_stored_ack_number(buffer_file)
