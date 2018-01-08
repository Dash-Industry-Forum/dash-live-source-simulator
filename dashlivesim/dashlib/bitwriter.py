""" Simple bitwriter class
"""

# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and contributor
# rights, including patent rights, and no such rights are granted under this license.
#
# Copyright (c) 2017, Dash Industry Forum.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#  * Redistributions of source code must retain the above copyright notice, this
#  list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright notice,
#  this list of conditions and the following disclaimer in the documentation and/or
#  other materials provided with the distribution.
#  * Neither the name of Dash Industry Forum nor the names of its
#  contributors may be used to endorse or promote products derived from this software
#  without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS AS IS AND ANY
#  EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#  WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#  IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
#  INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
#  NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
#  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.

LOWEST_BIT_MASKS = [(1 << pw) - 1 for pw in range(34)]


class Bitwriter(object):
    """ Simple class to write bits into a byte array
    """

    def __init__(self):
        self.byte_string = ""
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
            self.byte_string += chr(self.current_byte)
            self.current_byte = 0
            self.nr_bits_in_new_byte = 0
            nr_bits_left -= nr_bits_to_insert
            data &= LOWEST_BIT_MASKS[nr_bits_left]

        if nr_bits_left > 0:
            self.current_byte <<= nr_bits_left
            self.current_byte |= (data & LOWEST_BIT_MASKS[nr_bits_left])
            self.nr_bits_in_new_byte += nr_bits_left

    def add_bytes(self, byte_list):
        self.byte_string += "".join(b for b in byte_list)

    def get_bytes(self):
        return self.byte_string
