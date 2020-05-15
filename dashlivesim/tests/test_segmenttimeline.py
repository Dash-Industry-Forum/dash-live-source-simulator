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

from dashlivesim.tests.dash_test_util import VOD_CONFIG_DIR, CONTENT_ROOT, rm_outfile, write_data_to_outfile
from dashlivesim.dashlib import dash_proxy, mpd_proxy

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
        self.d = mpd_proxy.get_mpd(dp)
        self.root = ElementTree.fromstring(self.d)

    def testThatNumberTemplateFeaturesAreAbsent(self):
        testOutputFile = "segtimeline.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d.encode('utf-8'), testOutputFile)
        self.assertTrue(self.d.find("startNumber") == -1)  # There should be no startNumber in the MPD
        self.assertTrue(self.d.find("duration") == -1)  # There should be no duration in the segmentTemplate
        self.assertTrue(self.d.find("$Number$") == -1)  # There should be no $Number$ in template
        self.assertTrue(self.d.find("maxSegmentDuration") == -1)  # There should be no maxSegmentDuration in MPD

    def testThatSegmentTimeLineDataIsPresent(self):
        testOutputFile = "segtimeline.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d.encode('utf-8'), testOutputFile)
        self.assertTrue(self.d.find("$Time$") > 0)  # There should be $Time$ in the MPD

    def testThatTheLastSegmentReallyIsTheLatest(self):
        "Check that the last segment's end is less than one duration from now."
        period = self.root.find(node_ns('Period'))
        for adaptation_set in period.findall(node_ns('AdaptationSet')):
            segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
            timescale = int(segment_template.attrib['timescale'])
            segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
            s_elements = segment_timeline.findall(node_ns('S'))
            seg_start_time = None
            seg_end_time = None
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
        self.d = mpd_proxy.get_mpd(dp)
        self.root = ElementTree.fromstring(self.d)
        period = self.root.find(node_ns('Period'))
        for adaptation_set in period.findall(node_ns('AdaptationSet')):
            segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
            timescale = int(segment_template.attrib['timescale'])
            segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
            s_elements = segment_timeline.findall(node_ns('S'))
            seg_start_time = None
            seg_end_time = None
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


def find_first_audio_t(root):
    """Return t and d from the first audio segment."""
    period = root.find(node_ns('Period'))
    for adaptation_set in period.findall(node_ns('AdaptationSet')):
        content_type = adaptation_set.attrib['contentType']
        if content_type != 'audio':
            continue
        segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
        # timescale = int(segment_template.attrib['timescale'])
        segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
        first_s_elem = segment_timeline.find(node_ns('S'))
        first_t = int(first_s_elem.attrib['t'])
        first_d = int(first_s_elem.attrib['d'])
        return first_t, first_d
    raise ValueError("Could not find audio adaptation set")


class TestAvoidJump(unittest.TestCase):

    def testThatTimesDontJump(self):
        "Test that times don't jump as reported in ISSUE #91."

        # First get the MPD corresponding to 5.mpd.txt
        now = 1578681199
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = mpd_proxy.get_mpd(dp)
        root = ElementTree.fromstring(d)
        first_t, first_d = find_first_audio_t(root)
        # tsbd = 300 # TimeShiftBufferDepth
        self.assertTrue(now - first_t/48000 > 300, "Did not get before timeshift window start")

        later = now + 6
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=later)
        d = mpd_proxy.get_mpd(dp)
        root = ElementTree.fromstring(d)
        second_t, second_d = find_first_audio_t(root)
        self.assertEqual(second_t, first_t + first_d, "Second t is not first t + first d ")


class TestMPDWithSegmentTimelineWrap(unittest.TestCase):
    "Test that the MPD looks correct when wrapping."

    def testAfterWrap(self):
        self.now = 3610
        self.tsbd = 60
        urlParts = ['livesim', 'segtimeline_1', 'tsbd_%d' % self.tsbd, 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        self.d = mpd_proxy.get_mpd(dp)
        self.root = ElementTree.fromstring(self.d)
        nrSegments = self.getNrSegments(self.root)
        self.assertEqual(2*10, nrSegments)
        write_data_to_outfile(self.d.encode('utf-8'), "AfterWrap.mpd")

    def testBefore(self):
        self.now = 3590
        self.tsbd = 60
        urlParts = ['livesim', 'segtimeline_1', 'tsbd_%d' % self.tsbd,
                    'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT,
                                     now=self.now)
        self.d = mpd_proxy.get_mpd(dp)
        self.root = ElementTree.fromstring(self.d)
        nrSegments = self.getNrSegments(self.root)
        self.assertEqual(2*10, nrSegments)
        write_data_to_outfile(self.d.encode('utf-8'), "BeforeWrap.mpd")

    def getNrSegments(self, root):
        nrSegments = 0
        period = root.find(node_ns('Period'))
        aSets = period.findall(node_ns('AdaptationSet'))
        for aSet in aSets:
            sTempl = aSet.find(node_ns('SegmentTemplate'))
            sLines = sTempl.findall(node_ns('SegmentTimeline'))
            for sLine in sLines:
                sElems = sLine.findall(node_ns('S'))
                for sElem in sElems:
                    if 'r' in sElem.attrib:
                        nrSegments += int(sElem.attrib['r']) + 1
                    else:
                        nrSegments += 1
        return nrSegments


class TestSegmentTimelineInterval(unittest.TestCase):
    """SegmentTimeline with start, stop, timeoffset"""

    def setUp(self):
        self.now = 100
        urlParts = ['livesim', 'segtimeline_1', 'start_60', 'stop_120',
                    'timeoffset_0', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        self.d = mpd_proxy.get_mpd(dp)
        self.root = ElementTree.fromstring(self.d)

    def testSegmentList(self):
        period = self.root.find(node_ns('Period'))
        for adaptation_set in period.findall(node_ns('AdaptationSet')):
            content_type = adaptation_set.attrib['contentType']
            if content_type != "video":
                continue
            segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
            timescale = int(segment_template.attrib['timescale'])
            segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
            s_elements = segment_timeline.findall(node_ns('S'))
            seg_start_time = None
            seg_end_time = None
            for s_elem in s_elements:
                if seg_start_time is None:
                    seg_start_time = int(s_elem.attrib['t'])
                    self.assertEqual(60 * timescale, seg_start_time)
                else:
                    seg_start_time = seg_end_time
                nr_repeat = int(s_elem.attrib.get('r', 0))
                duration = int(s_elem.attrib['d'])
                seg_end_time = seg_start_time + duration * (1 + nr_repeat)
            last_end_time = seg_end_time / timescale
            self.assertLess(last_end_time, self.now)
            last_end_time_plus_duration = (seg_end_time + duration)/timescale
            self.assertGreater(last_end_time_plus_duration, self.now)


class TestMultiPeriodSegmentTimeline(unittest.TestCase):
    "Test that the MPD looks correct when segtimeline_1 and periods_60 are both defined."

    def setUp(self):
        self.now = 6003
        self.tsbd = 90
        urlParts = ['livesim', 'segtimeline_1', 'periods_60', 'tsbd_%d' % self.tsbd, 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        self.d = mpd_proxy.get_mpd(dp)

    def testThatThereAreMultiplePeriods(self):
        "Check that the first segment starts less than one period before now-tsbd."
        testOutputFile = "segtimeline_periods.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d.encode('utf-8'), testOutputFile)
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
        d = dash_proxy.get_media(dp)
        self.assertTrue(isinstance(d, bytes), "A segment is returned")

    def testThatTimeSegmentIsSameAsNumber(self):
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'A1', 't%d.m4s' % self.seg_time]
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        time_seg = dash_proxy.get_media(dp)
        urlParts = ['livesim', 'segtimeline_1', 'testpic', 'A1', '%d.m4s' % self.seg_nr]
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        nr_seg = dash_proxy.get_media(dp)
        self.assertEqual(len(time_seg), len(nr_seg))
        self.assertEqual(time_seg, nr_seg)


class TestMPDWithSegmentTimelineNumber(unittest.TestCase):
    "Test that the MPD looks correct when segtimelinenr_1 is defined."

    def setUp(self):
        self.now = 6003
        self.tsbd = 30
        urlParts = ['livesim', 'segtimelinenr_1', 'tsbd_%d' % self.tsbd,
                    'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("server.org", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=self.now)
        self.d = mpd_proxy.get_mpd(dp)
        self.root = ElementTree.fromstring(self.d)

    def testThatSomeFeaturesAreAbsent(self):
        testOutputFile = "segtimelinenr.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d.encode('utf-8'), testOutputFile)
        self.assertTrue(self.d.find("duration") == -1)  # There should be no duration in the segmentTemplate
        self.assertTrue(self.d.find("$Time$") == -1)  # There should be no
        # $Number$ in template
        self.assertTrue(self.d.find("maxSegmentDuration") == -1)  # There should be no maxSegmentDuration in MPD

    def testThatSegmentTimeLineDataIsPresent(self):
        testOutputFile = "segtimelinenr.mpd"
        rm_outfile(testOutputFile)
        write_data_to_outfile(self.d.encode('utf-8'), testOutputFile)
        self.assertTrue(self.d.find("$Number$") > 0, "$Number$ missing")

    def testThatFirstSegmentHasRightNumber(self):
        "Check that the first segment has the right number."
        duration_in_s = 6
        period = self.root.find(node_ns('Period'))
        for adaptation_set in period.findall(node_ns('AdaptationSet')):
            segment_template = adaptation_set.find(node_ns('SegmentTemplate'))
            timescale = int(segment_template.attrib['timescale'])
            start_number = int(segment_template.attrib['startNumber'])
            segment_timeline = segment_template.find(node_ns('SegmentTimeline'))
            first_s_elem = segment_timeline.find(node_ns('S'))
            first_start = int(first_s_elem.attrib['t'])
            duration = duration_in_s * timescale
            start_nr_from_time = int(round(1.0 * first_start / duration))
            self.assertEqual(start_number, start_nr_from_time)
