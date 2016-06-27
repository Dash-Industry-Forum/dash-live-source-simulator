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

import unittest

from dash_test_util import *
from dashlivesim.dashlib import mpdprocessor

vodMPD = join(CONTENT_ROOT, "testpic", "Manifest.mpd")

class TestMpdProcessor(unittest.TestCase):
    "Test of MPD parsing and writing"

    def setUp(self):
        self.cfg = {'scte35Present': False, 'utc_timing_methods': [], 'utc_head_url': "",
                    'continuous': False, 'segtimeline': False, 'now': 100000}

    def test_mpd_in_out(self):
        mp = mpdprocessor.MpdProcessor(vodMPD, self.cfg)
        mp.process({'availabilityStartTime': "1971", 'availability_start_time_in_s': 31536000,
                    'BaseURL': "http://india/", 'minimumUpdatePeriod': "0", 'periodOffset': 100000},
                   [{'id': "p0", 'startNumber': "0", 'presentationTimeOffset': 0},
                    {'id': "p1", 'startNumber': "3600", 'presentationTimeOffset': 100000}])
        xml = mp.get_full_xml()

    def test_utc_timing_head(self):
        self.cfg['utc_timing_methods'] = ["head"]
        mp = mpdprocessor.MpdProcessor(vodMPD, self.cfg)
        mp.process({'availabilityStartTime': "1971", 'availability_start_time_in_s': 31536000,
                    'BaseURL': "http://india/", 'minimumUpdatePeriod': "0", 'periodOffset': 100000},
                   [{'id': "p0", 'startNumber': "0", 'presentationTimeOffset': 0}])
        xml = mp.get_full_xml()
        head_pos = xml.find('<UTCTiming schemeIdUri="urn:mpeg:dash:utc:http-head:2014"')
        self.assertGreater(head_pos, 0, "UTCTiming for head method not found.")

    def test_utc_timing_direct_and_head(self):
        self.cfg['utc_timing_methods'] = ["direct", "head"]
        mp = mpdprocessor.MpdProcessor(vodMPD, self.cfg)
        mp.process({'availabilityStartTime': "1971", 'availability_start_time_in_s': 31536000,
                    'BaseURL': "http://india/", 'minimumUpdatePeriod': "0", 'periodOffset': 100000},
                   [{'id': "p0", 'startNumber': "0", 'presentationTimeOffset': 0}])
        xml = mp.get_full_xml()
        head_pos = xml.find('<UTCTiming schemeIdUri="urn:mpeg:dash:utc:http-head:2014"')
        direct_pos = xml.find('<UTCTiming schemeIdUri="urn:mpeg:dash:utc:direct:2014"')
        self.assertLess(direct_pos, head_pos, "UTCTiming direct method does not come before head method.")
