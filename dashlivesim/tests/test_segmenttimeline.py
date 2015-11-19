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

import unittest, sys

from dash_test_util import *
from ..dashlib import dash_proxy
from ..dashlib import mpdprocessor

class TestMPDWithSegmentTimeline(unittest.TestCase):
    "Test that the MPD looks correct when segtimeline_1 is defined."

    def setUp(self):
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=8000)
        self.d = dp.handle_request()

    def testThatNumberTemplateFeaturesAreAbsent(self):
        testOutputFile = "segtimeline.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d, testOutputFile)
        self.assertTrue(self.d.find("startNumber") == -1) # There should be no startNumber in the MPD
        self.assertTrue(self.d.find("duration") == -1) # There should be no duration in the segmentTemplate
        self.assertTrue(self.d.find("$Number$") == -1) # There should be no $Number$ in template
        self.assertTrue(self.d.find("maxSegmentDuration") == -1) # There should be no maxSegmentDuration in MPD

    def testThatSegmentTimeLineDataIsPresent(self):
        testOutputFile = "segtimeline.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d, testOutputFile)
        self.assertTrue(self.d.find("$Time$") > 0) # There should be no startNumber in the MPD

class TestMediaSegments(unittest.TestCase):
    "Test that media segments are served properly."

    def setUp(self):
        self.seg_nr = 349
        self.timescale = 48000
        self.duration = 6
        self.seg_time = self.seg_nr * self.duration * self.timescale
        self.now = (self.seg_nr+2)*self.duration

    def testThatTimeLookupWorks(self):
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'A1', 't%d.m4s' % self.seg_time]
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        d = dp.handle_request()
        self.assertTrue(isinstance(d, basestring), "A segment is returned")

    def testThatTimeSegmentIsSameAsNumber(self):
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'A1', 't%d.m4s' % self.seg_time]
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        time_seg = dp.handle_request()
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'A1', '%d.m4s' % self.seg_nr]
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        nr_seg = dp.handle_request()
        self.assertEqual(len(time_seg), len(nr_seg))
        self.assertEqual(time_seg, nr_seg)




