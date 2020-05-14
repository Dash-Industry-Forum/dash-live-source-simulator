""" Simple bitwriter class
"""

LOWEST_BIT_MASKS = [(1 << pw) - 1 for pw in range(34)]


class Bitwriter:
    """ Simple class to write bits into a byte array
    """

    def __init__(self):
        self.byte_string = bytearray()
        self.current_byte = 0
        self.nr_bits_in_new_byte = 0

    def __len__(self):
        return len(self.byte_string)

    def __getitem__(self, sliced):
        return self.byte_string[sliced]

    def add_bits(self, data, nr_bits):
        """Add an arbitrary number of bits from unsigned data.
        """

        nr_bits_left = nr_bits

        while nr_bits_left + self.nr_bits_in_new_byte >= 8:
            nr_bits_to_insert = 8 - self.nr_bits_in_new_byte
            bits = data >> (nr_bits_left - nr_bits_to_insert)
            self.current_byte <<= nr_bits_to_insert
            self.current_byte |= bits
            self.byte_string.append(self.current_byte)
            self.current_byte = 0
            self.nr_bits_in_new_byte = 0
            nr_bits_left -= nr_bits_to_insert
            data &= LOWEST_BIT_MASKS[nr_bits_left]

        if nr_bits_left > 0:
            self.current_byte <<= nr_bits_left
            self.current_byte |= (data & LOWEST_BIT_MASKS[nr_bits_left])
            self.nr_bits_in_new_byte += nr_bits_left

    def add_bytes(self, byte_list):
        self.byte_string.extend(byte_list)

    def get_bytes(self):
        return self.byte_string
