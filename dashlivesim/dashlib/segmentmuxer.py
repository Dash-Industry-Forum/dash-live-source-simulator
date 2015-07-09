"""Segment Muxer. Can multiplex DASH init and media segments (of some kinds).
"""

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

from .mp4filter import MP4Filter
from .structops import uint32_to_str, str_to_uint32


class InitSegmentStructure(MP4Filter):
    """Holds the structure of an initsegment.

    Stores ftyp, mvhd, trex, and trak box data."""

    def __init__(self, filename=None, data=None):
        MP4Filter.__init__(self, filename, data)
        self.top_level_boxes_to_parse = ['ftyp', 'moov']
        self.composite_boxes_to_parse = ['moov', 'mvex']
        self._ftyp = None
        self._mvhd = None
        self._trex = None
        self._trak = None

    def process_ftyp(self, data):
        "Get a handle to ftyp."
        self._ftyp = data
        return data

    def process_mvhd(self, data):
        "Get a handle to mvhd."
        self._mvhd = data
        return data

    def process_trex(self, data):
        "Get a handle to trex."
        self._trex = data
        return data

    def process_trak(self, data):
        "Get a handle to trak."
        self._trak = data
        return data

    @property
    def ftyp(self):
        "Get the ftyp box."
        return self._ftyp

    @property
    def trak(self):
        "Get the trak box."
        return self._trak

    @property
    def mvhd(self):
        "Get the mvhd box."
        return self._mvhd

    @property
    def trex(self):
        "Get the trex box."
        return self._trex


class MultiplexInits(object):
    "Takes two init segments and multiplexes them. The ftyp and mvhd is taken from the first."
    #pylint: disable=too-few-public-methods

    def __init__(self, filename1=None, filename2=None, data1=None, data2=None):
        self.istruct1 = InitSegmentStructure(filename1, data1)
        self.istruct1.filter()
        self.istruct2 = InitSegmentStructure(filename2, data2)
        self.istruct2.filter()

    def construct_muxed(self):
        "Construct a multiplexed init segment."
        data = []

        data.append(self.istruct1.ftyp)
        mvex_size = 8 + len(self.istruct1.trex) + len(self.istruct2.trex)
        moov_size = 8 + len(self.istruct1.mvhd) + mvex_size + len(self.istruct1.trak) + len(self.istruct2.trak)

        data.append(uint32_to_str(moov_size))
        data.append('moov')
        data.append(self.istruct1.mvhd)
        data.append(uint32_to_str(mvex_size))
        data.append('mvex')
        data.append(self.istruct1.trex)
        data.append(self.istruct2.trex)
        data.append(self.istruct1.trak)
        data.append(self.istruct2.trak)

        return "".join(data)


class MediaSegmentStructure(MP4Filter):
    "Holds the box structure of a media segment."
    # pylint: disable=too-many-instance-attributes

    def __init__(self, filename=None, data=None):
        MP4Filter.__init__(self, filename, data)
        self.top_level_boxes_to_parse = ['styp', 'moof', 'mdat']
        self.trun_data_offset = None
        self.trun_data_offset_in_traf = None
        self.traf_start = None
        self.styp = None
        self.mfhd = None
        self.traf = None
        self.moof = None
        self.mdat = None

    def parse_trun(self, data, pos):
        "Parse trun box and find position of data_offset."
        flags = str_to_uint32(data[8:12]) & 0xffffff
        data_offset_present = flags & 1
        if data_offset_present:
            self.trun_data_offset = str_to_uint32(data[16:20])
            self.trun_data_offset_in_traf = pos + 16 - self.traf_start

    def filter_box(self, boxtype, data, file_pos, path=""):
        "Filter box or tree of boxes recursively."
        if boxtype == "styp":
            self.styp = data
        elif boxtype == "moof":
            self.moof = data
        elif boxtype == "mdat":
            self.mdat = data
        elif boxtype == "mfhd":
            self.mfhd = data
        elif boxtype == "traf":
            self.traf = data
            self.traf_start = file_pos
        elif boxtype == "trun":
            self.parse_trun(data, file_pos)
        if path == "":
            path = boxtype
        else:
            path = "%s.%s" % (path, boxtype)
        output = ""
        if path in ("moof", "moof.traf"): # Go deeper
            output += data[:8]
            pos = 8
            while pos < len(data):
                size, boxtype = self.check_box(data[pos:pos+8])
                output += self.filter_box(boxtype, data[pos:pos+size], file_pos + len(output), path)
                pos += size
        else:
            output = data
        return output

class MultiplexMediaSegments(object):
    """Takes two media segments and multiplexes them like [mdat1][moof1][mdat2][moof2].

    The styp and is taken from the first."""

    def __init__(self, filename1=None, filename2=None, data1=None, data2=None):
        self.mstruct1 = MediaSegmentStructure(filename1, data1)
        self.mstruct1.filter()
        self.mstruct2 = MediaSegmentStructure(filename2, data2)
        self.mstruct2.filter()


    def mux_on_fragment_level(self):
        "Multiplex on frgment level."
        data = []
        data.append(self.mstruct1.styp)
        data.append(self.mstruct1.moof)
        data.append(self.mstruct1.mdat)
        data.append(self.mstruct2.moof)
        data.append(self.mstruct2.mdat)
        return "".join(data)

    def mux_on_sample_level(self):
        "Mux media samples into one mdata. This is done by simple concatenation."

        def get_traf_with_mod_offset(mstruct, delta_offset):
            "Get a traf box but with modified offset."
            if mstruct.trun_data_offset is None:
                return mstruct.traf
            new_data_offset = mstruct.trun_data_offset + delta_offset
            traf = mstruct.traf
            offset = mstruct.trun_data_offset_in_traf
            return traf[:offset] + uint32_to_str(new_data_offset) + traf[offset+4:]

        delta_offset1 = len(self.mstruct2.traf)
        delta_offset2 = len(self.mstruct1.traf) + len(self.mstruct1.mdat) - 8
        traf1 = get_traf_with_mod_offset(self.mstruct1, delta_offset1)
        traf2 = get_traf_with_mod_offset(self.mstruct2, delta_offset2)

        moof_size = 8 + len(self.mstruct1.mfhd) + len(self.mstruct1.traf) + len(self.mstruct2.traf)
        mdat_size = len(self.mstruct1.mdat) + len(self.mstruct2.mdat) - 8

        data = []
        data.append(self.mstruct1.styp)
        data.append(uint32_to_str(moof_size))
        data.append('moof')
        data.append(self.mstruct1.mfhd)
        data.append(traf1)
        data.append(traf2)
        data.append(uint32_to_str(mdat_size))
        data.append('mdat')
        data.append(self.mstruct1.mdat[8:])
        data.append(self.mstruct2.mdat[8:])

        return "".join(data)
