""" Simple bitreader class and some utility functions
"""

import struct


BYTE_UNPACK = struct.Struct("B").unpack_from


class bitreader:
    """ Class used to read bits from a byte buffer
    """

    def __init__(self, buffer):
        self.buffer = buffer
        self.bit_pos = 7
        self.byte = BYTE_UNPACK(self.buffer, 0)[0]
        self.index = 1
        self.bit = 0

    def get_bits(self, num_bits):
        """ Read bits from the buffer
        """

        num = 0
        mask = 1 << self.bit_pos

        while num_bits:
            num_bits -= 1
            self.bit += 1
            num <<= 1

            if self.byte & mask:
                num |= 1
            mask >>= 1
            self.bit_pos -= 1

            if self.bit_pos < 0:
                self.bit_pos = 7
                mask = 1 << self.bit_pos
                if self.index < len(self.buffer):
                    self.byte = BYTE_UNPACK(self.buffer, self.index)[0]
                else:
                    self.byte = 0
                self.index += 1

        return num

    def step_bytes(self, bytes):
        """ Returns an integer number of bytes from the buffer
        """

        data = self.buffer[self.index - 1: self.index - 1 + bytes]
        for i in range(bytes):
            self.get_bits(8)
        return data

    def tell(self):
        """ Returns the current byte position
        """

        return self.index

    def tell_bits(self):
        """Returns the current bit position."""
        return self.bit

    def remaining_bits(self):
        """Returns the remaining bits in the buffer."""
        return len(self.buffer) * 8 - self.bit


def read_bits(reader, num_bits, text, display, to_hex=False):
    """ Read bits from a bitreader and displays the output
    """

    num = reader.get_bits(num_bits)
    if display:
        if to_hex:
            print(f"{text:40}: 0x{num:02x}")
        else:
            print(f"{text:40}: {num}")

    return num


def ue(reader):
    """ Read one exponential golomb code using a bitreader

        H264 bitstreams often makes use of exponential golomb codes
    """

    leading_zero_bits = -1
    b = 0
    while not b:
        leading_zero_bits += 1
        b = reader.get_bits(1)
    return 2**leading_zero_bits - 1 + reader.get_bits(leading_zero_bits)
