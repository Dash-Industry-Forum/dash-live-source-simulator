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

from dashlivesim.tests.dash_test_util import rm_outfile, write_data_to_outfile, VOD_CONFIG_DIR, CONTENT_ROOT
from dashlivesim.dashlib import ttml_timing_offset
from dashlivesim.dashlib import dash_proxy, mpd_proxy

TEST_STRING_1 = b'< begin="01:02:03.1234" end="10:59:43:29" >'
TEST_STRING_SEG_NR = b'... Segment # 12 ...'


class TestTtmlTimingChange(unittest.TestCase):
    "Test that TTML string is changed properly."

    def testNoChange(self):
        "Offset is 0 seconds."
        outString = ttml_timing_offset.adjust_ttml_content(TEST_STRING_1, 0, None)
        self.assertEqual(outString, TEST_STRING_1)

    def testAdd1Hour(self):
        "Offset is 3600."
        outString = ttml_timing_offset.adjust_ttml_content(TEST_STRING_1, 3600, None)
        outGoal = b'< begin="02:02:03.1234" end="11:59:43:29" >'
        self.assertEqual(outString, outGoal)

    def testWrap(self):
        "Add an offset that wraps."
        outString = ttml_timing_offset.adjust_ttml_content(TEST_STRING_1, 360050, None)
        outGoal = b'< begin="101:02:53.1234" end="111:00:33:29" >'
        self.assertEqual(outString, outGoal)


class TestTtmlSegmentNrChange(unittest.TestCase):
    "Test that TTML string is changed properly."

    def testSetToRightNr(self):
        "Output Nr should be what is input."
        outString = ttml_timing_offset.adjust_ttml_content(TEST_STRING_SEG_NR, 360050, 22)
        outGoal = b'... Segment # 22 ...'
        self.assertEqual(outString, outGoal)


class TestSegmentModification(unittest.TestCase):

    def testTtmlSegment(self):
        testOutputFile = "sub.m4s"
        rm_outfile(testOutputFile)
        segmentNr = 718263000
        segment = "%d.m4s" % segmentNr
        now = segmentNr * 2 + 10
        urlParts = ['livsim', 'ato_inf', 'testpic_stpp', 'S1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        write_data_to_outfile(d, testOutputFile)
        self.assertTrue(d.find(b'begin="399035:00:00.000"') > 0)
        self.assertTrue(d.find(b'eng : UTC = 2015-07-10T11:00:00Z') > 0)


class TestMpdExtraction(unittest.TestCase):

    def testStartNumber(self):
        "Check that all 3 media components have startNumber=0"
        urlParts = ['livesim', 'testpic_stpp', 'Manifest_stpp.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = mpd_proxy.get_mpd(dp)
        self.assertEqual(d.count('startNumber="0'), 3)
