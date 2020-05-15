# The copyright in this software is being made available under the BSD License,
# included below. This software may be subject to other third party and contributor
# rights, including patent rights, and no such rights are granted under this license.
#
# Copyright (c) 2020, Dash Industry Forum.
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

import unittest

from dashlivesim.dashlib import ttml_timing_offset


TTML_IN = b'<p begin="00:00:00" end="01:00:00.25>Segment # 12 swe : 00:00:30</p>'
TTML_OUT = b'<p begin="00:00:22" end="01:00:22.25>Segment # 24 swe : UTC = 1970-01-01T00:00:52Z</p>'

# TIME_PATTERN_S = re.compile(rb'(?P<attr>(begin|end))="(?P<hours>\d\d):(?P<minutes>\d\d):(?P<seconds>\d\d)')
# CONTENT_PATTERN_S = re.compile(rb'(?P<lang>\w+) : (?P<hours>\d\d):(?P<minutes>\d\d):(?P<seconds>\d\d)(\.\d+)?')
# CONTENT_PATTERN_SEGMENT = re.compile(rb'(?P<intro>Segment # )(?P<seg_nr>\d+)')


class TestTTMLTimeUpdate(unittest.TestCase):

    def testUpdateTTMLTime(self):
        outbytes = ttml_timing_offset.adjust_ttml_content(TTML_IN, 22, 24)
        self.assertEqual(outbytes, TTML_OUT)
