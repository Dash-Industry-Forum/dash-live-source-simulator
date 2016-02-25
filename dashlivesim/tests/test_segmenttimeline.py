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
from xml.etree import ElementTree

from dash_test_util import *
from dashlivesim.dashlib import dash_proxy
from dashlivesim.dashlib import mpdprocessor

NAMESPACE = 'urn:mpeg:dash:schema:mpd:2011'

def node_ns(name):
    return '{%s}%s' % (NAMESPACE, name)

class TestMPDWithSegmentTimeline(unittest.TestCase):
    "Test that the MPD looks correct when segtimeline_1 is defined."

    def setUp(self):
        self.now = 6003
        self.tsbd = 30
        urlParts = ['livesim', 'segtimeline_1', 'tsbd_%d' % self.tsbd, 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        self.d = dp.handle_request()
        self.root = ElementTree.fromstring(self.d)

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
        self.assertTrue(self.d.find("$Time$") > 0) # There should be $Time$ in the MPD

    def testThatTheLastSegmentReallyIsTheLatest(self):
        "Check that the last segment's end is less than one duration from now."
        period = self.root.find(node_ns('Period'))
        for adaptation_set in period.findall(node_ns('AdaptationSet')):
            content_type = adaptation_set.attrib['contentType']
            segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
            timescale = int(segment_template.attrib['timescale'])
            segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
            s_elements = segment_timeline.findall(node_ns('S'))
            seg_start_time = None
            for s_elem in s_elements:
                if seg_start_time is None:
                    seg_start_time = int(s_elem.attrib['t'])
                else:
                    seg_start_time = seg_end_time
                nr_repeat = int(s_elem.attrib.get('r', 0))
                duration = int(s_elem.attrib['d'])
                seg_end_time = seg_start_time + duration * (1 + nr_repeat)
            last_end_time = seg_end_time / timescale
            self.assertLess(last_end_time, self.now)
            last_end_time_plus_duration = (seg_end_time + duration)/timescale
            self.assertGreater(last_end_time_plus_duration, self.now)

    def testThatTheLastSegmentReallyIsTheLatestAtWrapAround(self):
        "Check that the last segment's end is less than one duration from now at wraparound."
        self.now = 3603
        self.tsbd = 30
        urlParts = ['livesim', 'segtimeline_1', 'tsbd_%d' % self.tsbd, 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        self.d = dp.handle_request()
        self.root = ElementTree.fromstring(self.d)
        period = self.root.find(node_ns('Period'))
        for adaptation_set in period.findall(node_ns('AdaptationSet')):
            content_type = adaptation_set.attrib['contentType']
            segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
            timescale = int(segment_template.attrib['timescale'])
            segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
            s_elements = segment_timeline.findall(node_ns('S'))
            seg_start_time = None
            for s_elem in s_elements:
                if seg_start_time is None:
                    seg_start_time = int(s_elem.attrib['t'])
                else:
                    seg_start_time = seg_end_time
                nr_repeat = int(s_elem.attrib.get('r', 0))
                duration = int(s_elem.attrib['d'])
                seg_end_time = seg_start_time + duration * (1 + nr_repeat)
            last_end_time = seg_end_time / timescale
            self.assertLess(last_end_time, self.now)
            last_end_time_plus_duration = (seg_end_time + duration)/timescale
            self.assertGreater(last_end_time_plus_duration, self.now)

    def testThatFirstSegmentStartsJustBeforeTsbd(self):
        "Check that the first segment starts less than one period before now-tsbd."
        period = self.root.find(node_ns('Period'))
        for adaptation_set in period.findall(node_ns('AdaptationSet')):
            content_type = adaptation_set.attrib['contentType']
            segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
            timescale = int(segment_template.attrib['timescale'])
            segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
            first_s_elem = segment_timeline.find(node_ns('S'))
            first_start = int(first_s_elem.attrib['t'])
            duration = int(first_s_elem.attrib['d'])
            start_time = first_start / timescale
            start_time_plus_duration = (first_start + duration) / timescale
            self.assertLess(start_time, self.now - self.tsbd)
            self.assertGreater(start_time_plus_duration, self.now - self.tsbd)


class TestMultiPeriodSegmentTimeline(unittest.TestCase):
    "Test that the MPD looks correct when segtimeline_1 and periods_60 are both defined."

    def setUp(self):
        self.now = 6003
        self.tsbd = 90
        urlParts = ['livesim', 'segtimeline_1', 'periods_60', 'tsbd_%d' % self.tsbd, 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        self.d = dp.handle_request()


    def testThatThereAreMultiplePeriods(self):
        "Check that the first segment starts less than one period before now-tsbd."
        testOutputFile = "segtimeline_periods.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d, testOutputFile)
        self.root = ElementTree.fromstring(self.d)
        periods = self.root.findall(node_ns('Period'))
        self.assertGreater(len(periods), 1)


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
