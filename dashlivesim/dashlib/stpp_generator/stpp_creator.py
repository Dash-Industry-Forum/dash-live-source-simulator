"""Generate TTML init and media segments.

Start from template (which has timescale=1000)."""

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

from ..mp4filter import MP4Filter
from ..structops import uint32_to_str, str_to_uint32, uint64_to_str


TTML_MEDIA_TMPL = '\x00\x00\x00\x18stypmsdh\x00\x00\x00\x00msdhdash\x00\x00\x00`moof\x00\x00\x00\x10mfhd\x00\x00\
\x00\x00\x00\x00\x00\x01\x00\x00\x00Htraf\x00\x00\x00\x18tfhd\x00\x02\x00\x18\x00\x00\x00\x03\x00\x00\x03\xe8\x00\
\x00\x00\t\x00\x00\x00\x14tfdt\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x14trun\x00\x00\x00\
\x01\x00\x00\x00\x01\x00\x00\x00h\x00\x00\x00\x08mdat'

TIMESCALE = 1000 # This is the units for tfdt time and durations.
TRACK_ID = 3
# The init has sample_time_scale and trackID according to the values above
TTML_INIT = '\x00\x00\x00\x18ftypiso6\x00\x00\x00\x01isomdash\x00\x00\x02\x9dmoov\x00\x00\x00lmvhd\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc8\x00\x00\x00\x00\x00\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00@\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00(mvex\x00\x00\x00 trex\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x01\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x01trak\x00\x00\x00\\tkhd\x00\x00\x00\x07\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00@\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x9dmdia\x00\x00\x00 mdhd\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\xe8\x00\x00\x00\x00\x15\xc7\x00\x00\x00\x00\x00-hdlr\x00\x00\x00\x00\
\x00\x00\x00\x00subt\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00DASH-IF TTML\x00\x00\x00\x01Hminf\x00\x00\x00\x0c\
sthd\x00\x00\x00\x00\x00\x00\x00$dinf\x00\x00\x00\x1cdref\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x0curl \x00\x00\
\x00\x01\x00\x00\x01\x10stbl\x00\x00\x00\xc4stsd\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\xb4stpp\x00\x00\x00\x00\
\x00\x00\x00\x01http://www.w3.org/ns/ttml#parameter http://www.w3.org/ns/ttml http://www.w3.org/ns/ttml#styling http:\
//www.w3.org/ns/ttml#metadata urn:ebu:metadata urn:ebu:style\x00\x00\x00\x00\x00\x00\x10stts\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x10stsc\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x14stsz\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x10stco\x00\x00\x00\x00\x00\x00\x00\x00'


#EBU-TT-D sample
TTML_XML = u'''
<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns:ttp="http://www.w3.org/ns/ttml#parameter" xmlns="http://www.w3.org/ns/ttml"
    xmlns:tts="http://www.w3.org/ns/ttml#styling" xmlns:ttm="http://www.w3.org/ns/ttml#metadata"
    xmlns:ebuttm="urn:ebu:metadata" xmlns:ebutts="urn:ebu:style"
    xml:lang="en" xml:space="default"
    ttp:timeBase="media"
    ttp:cellResolution="32 15">
  <head>
    <metadata>
      <ttm:title>DASH-IF Live Simulator</ttm:title>
      <ebuttm:documentMetadata>
        <ebuttm:conformsToStandard>urn:ebu:distribution:2014-01</ebuttm:conformsToStandard>
        <ebuttm:authoredFrameRate>30</ebuttm:authoredFrameRate>
      </ebuttm:documentMetadata>
    </metadata>
    <styling>
      <style xml:id="s0" tts:fontStyle="normal" tts:fontFamily="sansSerif" tts:fontSize="100%" tts:lineHeight="normal"
      tts:color="#FFFFFF" tts:wrapOption="noWrap" tts:textAlign="center" />
      <style xml:id="s1" tts:color="#00FF00" tts:backgroundColor="#000000" ebutts:linePadding="0.5c"/>
    </styling>
    <layout>
      <region xml:id="r0" tts:origin="15% 80%" tts:extent="70% 20%" tts:overflow="visible" tts:displayAlign="before"/>
    </layout>
  </head>
  <body style="s0">
    <div region="r0">
      <p xml:id="s0" begin="00:00:00.00" end="00:00:01.00" >
        <span style="s2">The time is 00:00:00</span>
      </p>
      <p xml:id="s1" begin="00:00:01.00" end="00:00:02.80">
        <span>The time is 00:00:01</span>
      </p>
    </div>
  </body>
</tt>
'''


class StppSegmentCreatorError(Exception):
    "Error in TtmlSegmentGenerator."


class StppMediaFilter(MP4Filter):
    "Generate a TTML media segment with the limitation that there can only be one sample (<tt>)."

    def __init__(self, track_id, sequence_nr, sample_duration, tfdt_time, ttml_data):
        MP4Filter.__init__(self, data=TTML_MEDIA_TMPL)
        self.track_id = track_id
        self.sequence_nr = sequence_nr
        self.default_sample_duration = sample_duration
        self.tfdt_time = tfdt_time
        self.ttml_data = ttml_data
        self.top_level_boxes_to_parse = ['styp', 'moof', 'mdat', 'sidx']
        self.composite_boxes_to_parse = ['moof', 'traf']

    # pylint: disable=unused-argument, no-self-use
    def process_sidx(self, data):
        "SIDX not supported."
        raise StppSegmentCreatorError("SIDX presence not supported")

    def process_mfhd(self, data):
        "Set sequence number."
        return data[:12] + uint32_to_str(self.sequence_nr)

    def process_tfhd(self, data):
        "Process a tfhd box and set trackID, defaultSampleDuration and defaultSampleSize"
        tf_flags = str_to_uint32(data[8:12]) & 0xffffff
        assert tf_flags == 0x020018, "Can only handle certain tf_flags combinations"
        output = data[:12]
        output += uint32_to_str(self.track_id)
        output += uint32_to_str(self.default_sample_duration)
        output += uint32_to_str(len(self.ttml_data))
        return output

    def process_tfdt(self, data):
        "Process a tfdt box and set the baseMediaDecodeTime."
        version = ord(data[8])
        assert version == 1, "Can only handle tfdt version 1 (64-bit tfdt)."
        output = data[:12]
        output += uint64_to_str(self.tfdt_time)
        return output

    def process_mdat(self, data):
        "Make an mdat box with the right size to contain the one-and-only ttml sample."
        size = len(self.ttml_data) + 8
        return uint32_to_str(size) + 'mdat' + self.ttml_data


class StppInitFilter(MP4Filter):
    "Generate a TTML init segment from template by changing some values."

    def __init__(self, lang="eng", track_id=TRACK_ID, timescale=TIMESCALE, creation_modfication_time=None,
                 hdlr_name=None):
        "Filter to create an appropriate init segment."
        MP4Filter.__init__(self, data=TTML_INIT)
        self.lang = lang
        self.track_id = track_id
        self.timescale = timescale
        self.creation_modfication_time = creation_modfication_time # Measured from 1904-01-01 in seconds
        self.handler_name = hdlr_name
        self.top_level_boxes_to_parse = ['moov']
        self.composite_boxes_to_parse = ['moov', 'trak', 'mdia', 'minf', 'dinf']

    def process_mvhd(self, data):
        "Set nextTrackId and time and movie timescale."
        output = self._insert_timing_data(data)
        pos = len(output)
        output += data[pos:-4]
        output += uint32_to_str(self.track_id + 1) # next_track_ID
        return output

    def process_tkhd(self, data):
        "Set trackID and time."
        version = ord(data[8])
        output = data[:12]
        if version == 1:
            if self.creation_modfication_time:
                output += uint64_to_str(self.creation_modfication_time)
                output += uint64_to_str(self.creation_modfication_time)
            else:
                output += data[12:28]
            output += uint32_to_str(self.track_id)
            output += uint32_to_str(0)
            output += uint64_to_str(0) # duration
            pos = 44
        else:
            if self.creation_modfication_time:
                output += uint32_to_str(self.creation_modfication_time)
                output += uint32_to_str(self.creation_modfication_time)
            else:
                output += data[12:20]
            output += uint32_to_str(self.track_id)
            output += uint32_to_str(0)
            output += uint32_to_str(0) #duration
            pos = 32
        output += data[pos:]
        return output

    def process_mdhd(self, data):
        "Set the timescale for the trak, language and time."

        def get_char_bits(char):
            "Each character in the language is smaller case and offset at 0x60."
            return ord(char) - 96

        output = self._insert_timing_data(data)
        assert len(self.lang) == 3
        lang = self.lang
        lang_bits = (get_char_bits(lang[0]) << 10) + (get_char_bits(lang[1]) << 5) + get_char_bits(lang[2])
        output += uint32_to_str(lang_bits << 16)
        return output

    def process_hdlr(self, data):
        "Set handler name, if desired."
        hdlr = data[16:20]
        hdlr_name = data[32:-1] # Actually UTF-8 encoded
        print "Found hdlr %s: %s" % (hdlr, hdlr_name)
        if self.handler_name:
            output = uint32_to_str(len(self.handler_name) + 33) + data[4:32] + self.handler_name + '\x00'
            print "Wrote hdlr %s" % self.handler_name
        else:
            output = data
        return output

    def _insert_timing_data(self, data):
        "Help function to insert timestamps and timescale in similar boxes."
        version = ord(data[8])
        output = data[:12]
        if version == 1:
            if self.creation_modfication_time:
                output += uint64_to_str(self.creation_modfication_time)
                output += uint64_to_str(self.creation_modfication_time)
            else:
                output += data[12:28]
            output += uint32_to_str(self.timescale)
            output += uint64_to_str(0) # duration
        else:
            if self.creation_modfication_time:
                output += uint32_to_str(self.creation_modfication_time)
                output += uint32_to_str(self.creation_modfication_time)
            else:
                output += data[12:20]
            output += uint32_to_str(self.timescale)
            output += uint32_to_str(0)
        return output



def create_media_segment(track_id, sequence_nr, sample_duration, tfdt_time, ttml_data):
    "Create a media segment."
    ttml_seg = StppMediaFilter(track_id, sequence_nr, sample_duration, tfdt_time, ttml_data)
    return ttml_seg.filter()

def create_init_segment(lang="eng", track_id=TRACK_ID, timescale=TIMESCALE, creation_modfication_time=None,
                        hdlr_name=None):
    "Create an init segment."
    init_seg = StppInitFilter(lang, track_id, timescale, creation_modfication_time, hdlr_name)
    return init_seg.filter()
