"""Add an offset in seconds to TTML timing elements."""

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

import re, time

TIME_PATTERN_S = re.compile(r'(?P<attr>(begin|end))="(?P<hours>\d\d):(?P<minutes>\d\d):(?P<seconds>\d\d)')
CONTENT_PATTERN_S = re.compile(r'(?P<lang>\w+) : (?P<hours>\d\d):(?P<minutes>\d\d):(?P<seconds>\d\d)(\.\d+)?')
CONTENT_PATTERN_SEGMENT = re.compile(r'(?P<intro>Segment # )(?P<seg_nr>\d+)')

def adjust_ttml_content(xml_str, offset_in_s, output_seg_nr):
    "Add offset in seconds to begin and end elements in xml string."

    def replace(match_obj):
        "Replace function for the TIME_PATTERN_S."
        matches = match_obj.groupdict()
        attr = matches['attr']
        hours = int(matches['hours'])
        minutes = int(matches['minutes'])
        seconds = int(matches['seconds'])
        total_seconds = seconds + 60 * minutes + 3600 * hours + offset_in_s
        hours, seconds = divmod(total_seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return '%s="%02d:%02d:%02d' % (attr, hours, minutes, seconds)

    def replace_content(match_obj):
        "Replace function for the CONTENT_PATTERN_S."
        matches = match_obj.groupdict()
        hours = int(matches['hours'])
        minutes = int(matches['minutes'])
        seconds = int(matches['seconds'])
        total_seconds = seconds + 60 * minutes + 3600 * hours + offset_in_s
        time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(total_seconds))
        return '%s : UTC = %s' % (matches['lang'], time_str)

    def replace_segment_nr(match_obj):
        "Match and replace segment number."
        matches = match_obj.groupdict()
        return '%s%d' % (matches['intro'], output_seg_nr)

    xml_str = re.sub(TIME_PATTERN_S, replace, xml_str)
    xml_str = re.sub(CONTENT_PATTERN_S, replace_content, xml_str)
    xml_str = re.sub(CONTENT_PATTERN_SEGMENT, replace_segment_nr, xml_str)
    return xml_str
