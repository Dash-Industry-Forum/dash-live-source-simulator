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

from dashlivesim.tests.dash_test_util import VOD_CONFIG_DIR, CONTENT_ROOT
from dashlivesim.tests.dash_test_util import write_data_to_outfile
from dashlivesim.dashlib import dash_proxy
# from dashlivesim.dashlib import mpdprocessor


def isEmsgPresentInSegment(data):
    "Check if emsg box is present in segment."
    return data.find(b"emsg") >= 0


class TestSegTimelineLossMainLive(unittest.TestCase):
    "Test of Segment timeline loss signalling in MPD and segments for main live case"
    # def setUp(self):
    #   self.oldBaseUrlState = mpdprocessor.SET_BASEURL
    #   mpdprocessor.SET_BASEURL = True

    # def tearDown(self):
    #   mpdprocessor.SET_BASEURL = self.oldBaseUrlState

    def testNoInbandStreamElemInMPD(self):
        urlParts = ['livesim', 'baseurl_u10_d20', 'segtimeline_1', 'segtimelineloss_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=60)
        d = dp.handle_request()
        inbandEventElement = d.find('<InbandEventStream')
        self.assertLess(inbandEventElement, 0)

    def testInbandStreamElemInMPD(self):
        urlParts = ['livesim', 'baseurl_u10_d20', 'segtimeline_1', 'segtimelineloss_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10)
        d = dp.handle_request()
        inbandEventElement = d.find("<InbandEventStream")
        self.assertGreater(inbandEventElement, 0)

    def testNoEmsgInSegment(self):
        urlParts = ['livesim', 'baseurl_u10_d20', 'segtimeline_1', 'segtimelineloss_1', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=60)
        d = dp.handle_request()
        self.assertFalse(isEmsgPresentInSegment(d))

    def testEmsgInSegment(self):
        urlParts = ['livesim', 'baseurl_u10_d20', 'segtimeline_1', 'segtimelineloss_1', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10)
        d = dp.handle_request()
        self.assertTrue(isEmsgPresentInSegment(d))

    def testNoNewSegmentsAdded(self):
        urlParts = ['livesim', 'baseurl_u10_d20', 'segtimeline_1', 'segtimelineloss_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10)
        d = dp.handle_request()
        start = d.find('<SegmentTimeline>')
        end = d.find('</SegmentTimeline>')
        testOutputFile = "SegTimeline1.txt"
        segTimeline = d[start:end+18]
        write_data_to_outfile(d[start:end+18].encode('utf-8'), testOutputFile)
        dp2 = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=15)
        d2 = dp2.handle_request()
        start2 = d2.find('<SegmentTimeline>')
        end2 = d2.find('</SegmentTimeline>')
        testOutputFile = "SegTimeline2.txt"
        segTimeline2 = d2[start2:end2+18]
        write_data_to_outfile(d2[start2:end2+18].encode('utf-8'), testOutputFile)
        self.assertEqual(segTimeline, segTimeline2)

    def testNewSegmentsAdded(self):
        urlParts = ['livesim', 'baseurl_u10_d20', 'segtimeline_1', 'segtimelineloss_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10)
        d = dp.handle_request()
        start = d.find('<SegmentTimeline>')
        end = d.find('</SegmentTimeline>')
        testOutputFile = "SegTimeline3.txt"
        write_data_to_outfile(d[start:end+18].encode('utf-8'), testOutputFile)
        segTimeline = d[start:end+18]
        dp2 = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=31)
        d2 = dp2.handle_request()
        start2 = d2.find('<SegmentTimeline>')
        end2 = d2.find('</SegmentTimeline>')
        testOutputFile = "SegTimeline4.txt"
        write_data_to_outfile(d2[start2:end2+18].encode('utf-8'), testOutputFile)
        segTimeline2 = d2[start2:end2+18]
        self.assertNotEqual(segTimeline, segTimeline2)
