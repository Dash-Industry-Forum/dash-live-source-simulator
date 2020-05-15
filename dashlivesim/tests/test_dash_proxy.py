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
from os.path import join

from dashlivesim.tests.dash_test_util import VOD_CONFIG_DIR, CONTENT_ROOT
from dashlivesim.tests.dash_test_util import rm_outfile, write_data_to_outfile, findAllIndexes, OUT_DIR
from dashlivesim.dashlib import dash_proxy, mpd_proxy
from dashlivesim.dashlib import mpdprocessor
from dashlivesim.dashlib.mediasegmentfilter import MediaSegmentFilter


class TestMPDProcessing(unittest.TestCase):
    "Test of MPD parsing"

    def setUp(self):
        self.oldBaseUrlState = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = False

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.oldBaseUrlState

    def testMPDhandling(self):
        mpdprocessor.SET_BASEURL = True
        urlParts = ['pdash', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = mpd_proxy.get_mpd(dp)
        self.assertTrue(d.find("<BaseURL>http://streamtest.eu/pdash/testpic/</BaseURL>") > 0)

    def testMPDwithChangedAST(self):
        "Put AST to 1200s later than epoch start. There should be no PTO and startNumber=0 still."
        testOutputFile = "start.mpd"
        rm_outfile(testOutputFile)
        urlParts = ['pdash', 'start_1200', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = mpd_proxy.get_mpd(dp)
        write_data_to_outfile(d.encode('utf-8'), testOutputFile)
        self.assertTrue(d.find('availabilityStartTime="1970-01-01T00:20:00Z"') > 0)
        self.assertTrue(d.find('startNumber="0"') > 0)
        self.assertTrue(d.find('presentationTimeOffset') < 0)

    def testMPDwithStartandDur(self):
        urlParts = ['pdash', 'start_1200', 'dur_600', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=900)
        d = mpd_proxy.get_mpd(dp)
        if dash_proxy.PUBLISH_TIME:
            self.assertTrue(d.find('publishTime="1970-01-01T00:15:00Z"') > 0)
        self.assertTrue(d.find('availabilityEndTime="1970-01-01T00:30:00Z"') > 0)

    def testMPDwithStartand2Durations(self):
        urlParts = ['pdash', 'start_1200', 'dur_600', 'dur_300', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=900)
        d = mpd_proxy.get_mpd(dp)
        if dash_proxy.PUBLISH_TIME:
            self.assertTrue(d.find('publishTime="1970-01-01T00:15:00Z"') > 0)
        self.assertTrue(d.find('availabilityEndTime="1970-01-01T00:30:00Z"') > 0)
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=1795)
        d = mpd_proxy.get_mpd(dp)
        if dash_proxy.PUBLISH_TIME:
            self.assertTrue(d.find('publishTime="1970-01-01T00:29:00Z"') > 0)
        self.assertTrue(d.find('availabilityEndTime="1970-01-01T00:35:00Z"') > 0)

    def testHttpsBaseURL(self):
        "Check that protocol is set to https if signalled to DashProvider."
        mpdprocessor.SET_BASEURL = True
        urlParts = ['pdash', 'testpic', 'Manifest.mpd']
        is_https = 1
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0,
                                     is_https=is_https)
        d = mpd_proxy.get_mpd(dp)
        self.assertTrue(d.find("<BaseURL>https://streamtest.eu/pdash/testpic/</BaseURL>") > 0)

    def test_location_for_rel_times(self):
        mpdprocessor.SET_BASEURL = True
        urlParts = ['pdash', 'startrel_-20', 'stoprel_40', 'testpic',
                    'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT, now=1000)
        d = mpd_proxy.get_mpd(dp)
        self.assertTrue(d.find(
            'availabilityStartTime="1970-01-01T00:16:18Z"') > 0)
        self.assertTrue(d.find('startNumber="0"') > 0)
        self.assertTrue(d.find("<BaseURL>") < 0)
        self.assertTrue(
            d.find('<Location>http://streamtest.eu/pdash/start_978/stop_1044/'
                   'testpic/Manifest.mpd</Location>') > 0)

    def test_location_for_rel_times_zero_offset(self):
        mpdprocessor.SET_BASEURL = True
        urlParts = ['pdash', 'startrel_-20', 'stoprel_40', 'timeoffset_0',
                    'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT, now=1000)
        d = mpd_proxy.get_mpd(dp)
        self.assertTrue(d.find(
            'availabilityStartTime="1970-01-01T00:16:18Z"') > 0)
        self.assertTrue(d.find('startNumber="163"') > 0)
        self.assertTrue(d.find('presentationTimeOffset="978"') > 0)
        self.assertTrue(d.find("<BaseURL>") < 0)
        self.assertTrue(
            d.find('<Location>http://streamtest.eu/pdash/start_978/stop_1044/'
                   'timeoffset_0/testpic/Manifest.mpd</Location>') > 0)

    def test_absolute_times(self):
        mpdprocessor.SET_BASEURL = True
        urlParts = ['pdash', 'start_978', 'stop_1044', 'testpic',
                    'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT, now=1000)
        d = mpd_proxy.get_mpd(dp)
        self.assertTrue(d.find(
            'availabilityStartTime="1970-01-01T00:16:18Z"') > 0)
        self.assertTrue(d.find("<BaseURL>") > 0)
        self.assertTrue(d.find('<Location>') < 0)
        self.assertTrue(d.find('type="dynamic"') > 0)
        self.assertTrue(d.find('mediaPresentationDuration="PT1M6S') > 0)
        self.assertTrue(d.find('minimumUpdatePeriod') > 0)

    def test_absolute_times_after_stop(self):
        mpdprocessor.SET_BASEURL = True
        urlParts = ['pdash', 'start_978', 'stop_1044', 'testpic',
                    'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT, now=1046)
        d = mpd_proxy.get_mpd(dp)
        self.assertTrue(d.find(
            'availabilityStartTime="1970-01-01T00:16:18Z"') > 0)
        self.assertTrue(d.find('type="static"') > 0)
        self.assertTrue(d.find('mediaPresentationDuration="PT1M6S') > 0)
        self.assertTrue(d.find('minimumUpdatePeriod') < 0)


class TestInitSegmentProcessing(unittest.TestCase):
    def testInit(self):
        urlParts = ['pdash', 'testpic', 'A1', 'init.mp4']
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dash_proxy.get_init(dp)
        self.assertEqual(len(d), 651)


class TestMediaSegments(unittest.TestCase):

    def testMediaSegmentForTfdt32(self):
        testOutputFile = "t1.m4s"
        rm_outfile(testOutputFile)
        now = 2101  # 1s after start of segment 350
        segment = "349.m4s"
        urlParts = ['pdash', 'tfdt_32', 'testpic', 'A1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        write_data_to_outfile(d, testOutputFile)
        self.assertEqual(len(d), 39517)

    def testMediaSegmentTooEarly(self):
        urlParts = ['pdash', 'testpic', 'A1', '5.m4s']  # Should be available after 36s
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=34)
        d = dash_proxy.get_media(dp)
        self.assertEqual(d['ok'], False)

    def testMediaSegmentTooEarlyWithAST(self):
        urlParts = ['pdash', 'start_6', 'testpic', 'A1', '0.m4s']  # Should be available after 12s
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10)
        d = dash_proxy.get_media(dp)
        self.assertEqual(d['ok'], False)
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=14)
        d = dash_proxy.get_media(dp)
        self.assertEqual(len(d), 40346)  # A full media segment

    def testMediaSegmentBeforeTimeShiftBufferDepth(self):
        now = 1356999060
        segment = "%d.m4s" % ((now-330)/6)
        urlParts = ['pdash', 'testpic', 'A1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        self.assertEqual(d['ok'], False)

    def testLastMediaSegment(self):
        """With total duration of 2100, the last segment shall be 349
        (independent of start) and available at 4101 start+dur_1800+dur_300."""
        urlParts = ['pdash', 'start_2000', 'dur_1800', 'dur_300', 'testpic', 'A1', '349.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT, now=4101)
        d = dash_proxy.get_media(dp)
        # print "LMSG at %d" % d.find("lmsg")
        self.assertEqual(d.find(b"lmsg"), 24)

    def testMultiPeriod(self):
        testOutputFile = "multiperiod.mpd"
        rm_outfile(testOutputFile)
        urlParts = ['pdash', 'periods_10', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=3602)
        d = mpd_proxy.get_mpd(dp)
        write_data_to_outfile(d.encode('utf-8'), testOutputFile)
        periodPositions = findAllIndexes("<Period", d)
        self.assertEqual(len(periodPositions), 2)

    def testContinuous(self):
        testOutputFile = "ContMultiperiod.mpd"
        rm_outfile(testOutputFile)
        urlParts = ['pdash', 'continuous_1', 'periods_10', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=3602)
        d = mpd_proxy.get_mpd(dp)
        write_data_to_outfile(d.encode('utf-8'), testOutputFile)
        periodPositions = findAllIndexes("urn:mpeg:dash:period_continuity:2014", d)
        self.assertGreater(len(periodPositions), 1)

    def testUtcTiming(self):
        "Test that direct and head works."
        urlParts = ['pdash', 'utc_direct-head', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = mpd_proxy.get_mpd(dp)
        head_pos = d.find('<UTCTiming schemeIdUri="urn:mpeg:dash:utc:http-head:2014" '
                          'value="http://streamtest.eu/dash/time.txt" />')
        direct_pos = d.find('<UTCTiming schemeIdUri="urn:mpeg:dash:utc:direct:2014"')
        self.assertLess(direct_pos, head_pos)

    def testMediaSegmentInIntervalWithoutOffset(self):
        "Check that segment 5 is available after an hour."
        urlParts = ['pdash', 'start_3600', 'stop_3660',
                    'testpic', 'A1', '5.m4s']
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT, now=3650)
        d = dash_proxy.get_media(dp)
        self.assertEqual(d[4:8], b'styp')

    def testMediaSegmentInIntervalWithOffset(self):
        "Check that segment 605 is available after an hour."
        urlParts = ['pdash', 'start_3540', 'stop_3660',
                    'timeoffset_0', 'testpic', 'A1', '605.m4s']
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None,
                                     VOD_CONFIG_DIR, CONTENT_ROOT, now=3650)
        d = dash_proxy.get_media(dp)
        self.assertEqual(d[4:8], b'styp')

    def testMediaSegmentWithSidx(self):
        testOutputFile = "t1_sidx.m4s"
        rm_outfile(testOutputFile)
        now = 2101  # 1s after start of segment 350
        segment = "349.m4s"
        urlParts = ['pdash', 'sidx_1', 'testpic', 'A1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        write_data_to_outfile(d, testOutputFile)

    def testMediaIntervalWithOffset(self):
        "Test that only segments 590-609 are available"

        def get_segment(nr, now):
            urlParts = ['pdash', 'start_3540', 'stop_3660',
                        'timeoffset_0', 'testpic', 'A1', '%d.m4s' % nr]
            dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None,
                                         VOD_CONFIG_DIR, CONTENT_ROOT, now)
            return dash_proxy.get_media(dp)
        res = get_segment(589, 3600)
        self.assertEqual(res['ok'], False)
        res = get_segment(590, 3600)
        self.assertEqual(res[4:8], b'styp')
        res = get_segment(609, 3670)
        self.assertEqual(res[4:8], b'styp')
        res = get_segment(610, 3670)
        self.assertEqual(res['ok'], False)


class TestMorePathLevels(unittest.TestCase):
    "Test when representations are further down in"

    def setUp(self):
        self.oldBaseUrlState = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = False

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.oldBaseUrlState

    def testMPDGet(self):
        mpdprocessor.SET_BASEURL = True
        urlParts = ['pdash', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = mpd_proxy.get_mpd(dp)
        self.assertGreater(d.find("<BaseURL>http://streamtest.eu/pdash/testpic/</BaseURL>"), 0)

    def testInit(self):
        urlParts = ['pdash', 'testpic', 'en', 'A1', 'init.mp4']
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dash_proxy.get_init(dp)
        self.assertEqual(len(d), 617)

    def testMediaSegment(self):
        testOutputFile = "t2.m4s"
        rm_outfile(testOutputFile)
        now = 1356998460
        segment = "%d.m4s" % ((now-60)//6)
        urlParts = ['pdash', 'testpic', 'en', 'A1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        write_data_to_outfile(d, testOutputFile)


class TestTfdt(unittest.TestCase):
    "Test that the tfdt rewrite is working correctly"

    def testMediaSegment(self):
        testOutputFile = "tfdt.m4s"
        rm_outfile(testOutputFile)
        now = 1356998460
        segment = "%d.m4s" % ((now-60)//6)
        urlParts = ['pdash', 'testpic', 'A1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        write_data_to_outfile(d, testOutputFile)

    def testTfdtValueFromZero(self):
        "Tfdt value = mediaPresentationTime which corresponds to segmentNr*duration"
        now = 1393936560
        segNr = 232322749
        segment = "%d.m4s" % segNr
        urlParts = ['pdash', 'testpic', 'V1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        rm_outfile('tmp.m4s')
        tmp_name = join(OUT_DIR, 'tmp.m4s')
        with open(tmp_name, 'wb') as ofh:
            ofh.write(d)
        mf = MediaSegmentFilter(tmp_name)
        mf.filter()
        rm_outfile('tmp.m4s')
        tfdtValue = mf.tfdt_value
        presentationTime = tfdtValue // 90000
        segmentTime = segNr * 6
        self.assertEqual(presentationTime, segmentTime)

    def testThatNoPresentationTimeOffsetForTfdt32(self):
        now = 1393936560
        # segNr = 232322749
        urlParts = ['pdash', 'tfdt_32', 'testpic', 'V1', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = mpd_proxy.get_mpd(dp)
        self.assertFalse(d.find('presentationTimeOffset') > 0)


class TestInitMux(unittest.TestCase):

    def testInitMux(self):
        testOutputFile = "test_mux_init.mp4"
        rm_outfile(testOutputFile)
        now = 1356998460
        urlParts = ['pdash', 'testpic', 'V1__A1', "init.mp4"]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_init(dp)
        write_data_to_outfile(d, testOutputFile)

    def testMediaMux(self):
        testOutputFile = "test_mux.m4s"
        rm_outfile(testOutputFile)
        now = 1356998460
        segment = "%d.m4s" % ((now-60)//6)
        urlParts = ['pdash', 'testpic', 'V1__A1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        write_data_to_outfile(d, testOutputFile)


class TestScte35Manifest(unittest.TestCase):

    def setUp(self):
        now = 1356998460
        urlParts = ['pdash', 'scte35_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        self.mpd = mpd_proxy.get_mpd(dp)

    def test_scte35_profile_presence(self):
        self.assertTrue(self.mpd.find(",http://dashif.org/guidelines/adin/app") > 0)

    def test_inband_stream_signal(self):
        self.assertTrue(self.mpd.find('<InbandEventStream schemeIdUri="urn:scte:scte35:2013:xml"') > 0)


class TestScte35Segments(unittest.TestCase):

    def testScte35Event(self):
        testOutputFile = "seg_scte35.m4s"
        rm_outfile(testOutputFile)
        segDur = 6
        segNr = 1800000
        now = segNr*segDur+50
        segment = "%d.m4s" % segNr
        urlParts = ['pdash', 'scte35_3', 'testpic', 'V1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        self.assertEqual(d.find(b'emsg'), 28)
        write_data_to_outfile(d, testOutputFile)

    def testNoScte35Event(self):
        segDur = 6
        segNr = 1800001
        now = segNr*segDur+50
        segment = "%d.m4s" % segNr
        urlParts = ['pdash', 'scte35_1', 'testpic', 'V1', segment]
        dp = dash_proxy.DashProvider("127.0.0.1", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
        d = dash_proxy.get_media(dp)
        self.assertEqual(d.find(b'emsg'), -1)
