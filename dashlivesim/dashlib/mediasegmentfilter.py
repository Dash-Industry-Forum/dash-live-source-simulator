"""Filter media segment for live streams."""

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

from . import scte35
from .mp4filter import MP4Filter
from .structops import str_to_uint32, uint32_to_str, str_to_uint64, uint64_to_str, str_to_sint32, sint32_to_str
from .ttml_timing_offset import adjust_ttml_content

KEEP_SIDX = False


class MediaSegmentFilterError(Exception):
    "Error in MediaSegmentFilter."

class MediaSegmentFilter(MP4Filter):
    """Filter the fragment response to fill in the right seg_nr, tfdtTime and SCTE-35 cue.

    Make sidx 64-bit if needed."""

    #pylint: disable=too-many-instance-attributes, too-many-arguments
    def __init__(self, file_name, seg_nr=None, seg_duration=1, offset=0, lmsg=False, track_timescale=None,
                 scte35_per_minute=0, rel_path=None, is_ttml=False):
        MP4Filter.__init__(self, file_name)
        self.top_level_boxes_to_parse = ["styp", "sidx", "moof", "mdat"]
        self.composite_boxes_to_parse = ['moof', 'traf']
        self.seg_nr = seg_nr
        self.seg_duration = seg_duration
        self.offset = offset
        self.track_timescale = track_timescale
        self.rel_path = rel_path
        self.lmsg = lmsg
        self.size_change = 0
        self.tfdt_value = None # For testing
        self.duration = None
        self.scte35_per_minute = scte35_per_minute
        self.is_ttml = is_ttml
        self.ttml_size = None

        if self.is_ttml:
            self.data = self.find_and_process_mdat(self.data)

    #pylint: disable=no-self-use
    def process_styp(self, data):
        "Process styp and make sure lmsg presence follows the lmsg flag parameter. Add scte35 box if appropriate"
        lmsg = self.lmsg
        output = ""
        size = str_to_uint32(data[:4])
        pos = 8
        brands = []
        while pos < size:
            brand = data[pos:pos+4]
            if brand != "lmsg":
                brands.append(brand)
            pos += 4
        if lmsg:
            brands.append("lmsg")
        new_size = 8 + 4*len(brands)
        output += uint32_to_str(new_size)
        output += "styp"
        for brand in brands:
            output += brand
        scte35box = self.create_scte35box()
        output += scte35box
        return output

    def process_tfhd(self, data):
        "Process tfhd (assuming that we know the ttml size size)."
        if not self.is_ttml:
            return data
        tf_flags = str_to_uint32(data[8:12]) & 0xffffff
        pos = 16
        if tf_flags & 0x01:
            raise MediaSegmentFilterError("base-data-offset-present not supported in ttml segments")
        if tf_flags & 0x02:
            pos += 4
        if tf_flags & 0x08 == 0:
            raise MediaSegmentFilterError("Cannot handle ttml segments with default_sample_duration absent")
        else:
            pos += 4
        output = data[:pos]
        if tf_flags & 0x10:
            #old_ttml__size = str_to_uint32(data[pos:pos+4])
            output += uint32_to_str(self.ttml_size)
            #print "Changed ttml sample size from %d to %d" % (old_ttml__size, self.ttml_size)
            pos += 4
        else:
            raise MediaSegmentFilterError("Cannot handle ttml segments if default_sample_size_offset is absent")
        output += data[pos:]
        return output

    def process_mfhd(self, data):
        "Process mfhd box and set segmentNumber if requested."
        if self.seg_nr is None:
            return data
        else:
            return data[0:12] + uint32_to_str(self.seg_nr)

    def process_trun(self, data):
        "Get total duration from trun. Fix offset if self.size_change is non-zero."
        flags = str_to_uint32(data[8:12]) & 0xffffff
        sample_count = str_to_uint32(data[12:16])
        pos = 16
        data_offset_present = False
        if flags & 0x1: # Data offset present
            data_offset_present = True
            pos += 4
        if flags & 0x4:
            pos += 4 # First sample flags present
        sample_duration_present = flags & 0x100
        sample_size_present = flags & 0x200
        sample_flags_present = flags & 0x400
        sample_comp_time_present = flags & 0x800
        duration = 0
        for _ in range(sample_count):
            if sample_duration_present:
                duration += str_to_uint32(data[pos:pos+4])
                pos += 4
            if sample_size_present:
                pos += 4
            if sample_flags_present:
                pos += 4
            if sample_comp_time_present:
                pos += 4
        self.duration = duration

        #Modify data_offset
        output = data[:16]
        if data_offset_present and self.size_change > 0:
            offset = str_to_sint32(data[16:20])
            offset += self.size_change
            output += sint32_to_str(offset)
        else:
            output += data[16:20]
        output += data[20:]
        return output

    def process_sidx(self, data):
        "Process sidx data and add to output."
        if not KEEP_SIDX:
            return ""
        output = ""
        version = ord(data[8])
        timescale = str_to_uint32(data[16:20])
        if version == 0:
            #print "Changing sidx version to 1"
            size = str_to_uint32(data[0:4])
            #print "size is %d" % size
            sidx_size_expansion = 8
            output += uint32_to_str(size+sidx_size_expansion)
            output += data[4:8]
            output += chr(1)
            output += data[9:20]
            earliest_presentation_time = str_to_uint32(data[20:24])
            first_offset = str_to_uint32(data[24:28])
        else:
            output += data[0:20]
            earliest_presentation_time = str_to_uint64(data[20:28])
            first_offset = str_to_uint64(data[28:36])
        new_presentation_time = earliest_presentation_time + timescale*self.offset
        output += uint64_to_str(new_presentation_time)
        output += uint64_to_str(first_offset)
        if version == 0:
            output += data[28:]
        else:
            output += data[36:]
        return output

    def process_tfdt_to_64bit(self, data, output):
        """Generate new timestamps for tfdt and change size of boxes above if needed.

        Note that the input output will be returned and can have another size."""
        version = ord(data[8])
        tfdt_offset = self.offset*self.track_timescale
        if version == 0: # 32-bit baseMediaDecodeTime
            self.size_change = 4
            output = uint32_to_str(str_to_uint32(data[:4]) + self.size_change)
            output += data[4:8]
            output += chr(1)
            output += data[9:12]
            base_media_decode_time = str_to_uint32(data[12:16])
        else: # 64-bit
            output = data[:12]
            base_media_decode_time = str_to_uint64(data[12:20])
        new_base_media_decode_time = base_media_decode_time + tfdt_offset
        output += uint64_to_str(new_base_media_decode_time)
        self.tfdt_value = new_base_media_decode_time
        return output

    def process_tfdt(self, data):
        """Generate new timestamps for tfdt and change size of boxes above if needed.

       Try to keep in 32 bits if possible."""
        version = ord(data[8])
        if self.track_timescale is not None:
            tfdt_offset = self.offset*self.track_timescale
        else:
            tfdt_offset = 0
        if version == 0: # 32-bit baseMediaDecodeTime
            base_media_decode_time = str_to_uint32(data[12:16])
            new_base_media_decode_time = base_media_decode_time + tfdt_offset
            if new_base_media_decode_time < 4294967296:
                output = data[:12]
                output += uint32_to_str(new_base_media_decode_time)
            else:
                #print "Forced to change to 64-bit tfdt."
                self.size_change = 4
                output = uint32_to_str(str_to_uint32(data[:4]) + self.size_change)
                output += data[4:8]
                output += chr(1)
                output += data[9:12]
                output += uint64_to_str(new_base_media_decode_time)
        else: # 64-bit
            #print "Staying at 64-bit tfdt."
            output = data[:12]
            base_media_decode_time = str_to_uint64(data[12:20])
            new_base_media_decode_time = base_media_decode_time + tfdt_offset
            output += uint64_to_str(new_base_media_decode_time)
        self.tfdt_value = new_base_media_decode_time
        return output

    def get_tfdt_value(self):
        "Get the earliest presentation time value from tfdt box."
        return self.tfdt_value

    def get_duration(self):
        "Get total duration from trun."
        return self.duration

    def create_scte35box(self):
        """Create an Scte35 emsg box if at the right instance.

        Depending on scte35_per_minute, the splice inserts are as follows::
        1: 10s after full minute
        2: 10s and 40s after full minute
        3: 10, 30, 50s after full minute
        The SCTE35 message are coming in a segment that covers the time 8-6 s in advance.
        """
        ad_duration = 10
        if self.scte35_per_minute < 1 or self.scte35_per_minute > 8:
            return ""
        seg_starttime = self.seg_nr*self.seg_duration # StartTime in seconds
        sec_modulo_minute = seg_starttime % 60
        minute_start = seg_starttime - sec_modulo_minute
        splice_insert_times = [minute_start + 10]
        if self.scte35_per_minute == 2:
            splice_insert_times.append(minute_start+40)
        elif self.scte35_per_minute == 3:
            splice_insert_times.append(minute_start+36)
            splice_insert_times.append(minute_start+46)
        elif self.scte35_per_minute == 8:
            splice_insert_times.append(minute_start+30)
            ad_duration = 20
        found_splice_time = -1
        splice_time = None
        seg_endtime = seg_starttime + self.seg_duration
        for splice_time in splice_insert_times: # Assume that there are events 8s and 6s before the actual splice
            for pre_warning_time in (splice_time - 6, splice_time-8):
                if seg_starttime <= pre_warning_time <= seg_endtime:
                    found_splice_time = splice_time
                    break
            if found_splice_time >= 0:
                break
        if found_splice_time < 0:
            return "" # Nothing for this segment
        timescale = 90000 # Timescale
        emsg_id = splice_id = splice_time//10
        emsg = scte35.create_scte35_emsg(timescale, seg_starttime*timescale, found_splice_time*timescale,
                                         ad_duration*timescale, emsg_id, splice_id)
        #print "Made scte35 emsg %d" % len(emsg)
        return emsg

    def find_and_process_mdat(self, data):
        "Change the ttml part of mdat and update mdat size. Return full new data."
        pos = 0
        output = ""
        while pos < len(data):
            size = str_to_uint32(data[pos:pos+4])
            boxtype = data[pos+4:pos+8]
            if boxtype != 'mdat':
                output += data[pos:pos+size]
            else:
                output += self.update_ttml_mdat(data[pos:pos+size])
            pos += size
        return output

    def update_ttml_mdat(self, data):
        "Update the ttml payload of mdat and its size."
        ttml_xml = data[8:]
        ttml_out = adjust_ttml_content(ttml_xml, self.offset, self.seg_nr)
        self.ttml_size = len(ttml_out)
        out_size = self.ttml_size + 8
        return uint32_to_str(out_size) + 'mdat' + ttml_out
