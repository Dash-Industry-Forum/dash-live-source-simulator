"""Filter initialization segments (extract data and modify)."""

# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and contributor
# rights, including patent rights, and no such rights are granted under this license.
#
# Copyright (c) 2015, Dash Industry Forum.
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

from .structops import str_to_uint32
from .mp4filter import MP4Filter

class InitFilter(MP4Filter):
    "Filter init segment file and extract track timescale."

    def __init__(self, filename=None, data=None):
        MP4Filter.__init__(self, filename, data)
        self.top_level_boxes_to_parse = ['moov']
        self.composite_boxes_to_parse = ['moov', 'trak', 'mdia']
        self._track_timescale = -1
        self._track_id = None
        self._handler_type = None

    def process_hdlr(self, data):
        "Find the track type."
        self._handler_type = data[16:20]
        return data

    def process_tkhd(self, data):
        "Filter track header box and find track_id."
        assert self.track_id is None, "Multiple tracks in init file %s. Not supported." % self.filename
        version = ord(data[8])
        if version == 0:
            self._track_id = str_to_uint32(data[20:24])
        elif version == 1:
            self._track_id = str_to_uint32(data[28:32])
        return data

    def process_mdhd(self, data):
        "Process mdhd to get track_timscale."
        self._track_timescale = str_to_uint32(data[20:24])
        return data

    @property
    def track_timescale(self):
        "Get timescale for track."
        return self._track_timescale

    @property
    def handler_type(self):
        "Get handler type."
        return self._handler_type

    @property
    def track_id(self):
        "Get trackID for the single track in file."
        return self._track_id


class InitLiveFilter(MP4Filter):
    "Process an init segment file and set the durations to 0."

    # pylint: disable=too-many-branches, no-self-use

    def __init__(self, file_name=None, data=None):
        MP4Filter.__init__(self, file_name, data)
        self.top_level_boxes_to_parse = ['moov']
        self.composite_boxes_to_parse = ['moov', 'trak', 'mdia']
        self.movie_timescale = -1

    def process_mvhd(self, data):
        "Set duration in mvhd."
        version = ord(data[8])
        output = ""
        if version == 1:
            self.movie_timescale = str_to_uint32(data[28:32])
            output += data[:32]
            output += '\x00'*8 # duration
            output += data[40:]
        else: # version = 0
            self.movie_timescale = str_to_uint32(data[20:24])
            output += data[:24]
            output += '\x00'*4 # duration
            output += data[28:]
        return output

    def process_tkhd(self, data):
        "Set track duration."
        version = ord(data[8])
        output = ""
        if version == 1:
            output += data[:36]
            output += '\x00'*8 # duration
            output += data[44:]
        else: # version = 0
            output += data[:28]
            output += '\x00'*4 # duration
            output += data[32:]
        return output

    def process_mdhd(self, data):
        "Set media duration."
        output = ""
        version = ord(data[8])
        if version == 1:
            output += data[:32]
            output += '\x00'*8 # duration
            output += data[40:]
        else: # version = 0
            output += data[:24]
            output += '\x00'*4 # duration
            output += data[28:]
        return output
