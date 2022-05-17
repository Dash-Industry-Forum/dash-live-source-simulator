import unittest

from dashlivesim.tests.dash_test_util import VOD_CONFIG_DIR, CONTENT_ROOT
from dashlivesim.dashlib import mpd_proxy, dash_proxy
from dashlivesim.dashlib import mpdprocessor


class TestLowLatencyMPD(unittest.TestCase):
    "Test that low-latency MPD has the right attributes"

    def setUp(self):
        self.oldBaseUrlState = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = False

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.oldBaseUrlState

    def testCorrectFieldsInMPD(self):
        mpdprocessor.SET_BASEURL = True
        urlParts = ['livesim', 'chunkdur_1', 'ato_7', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = mpd_proxy.get_mpd(dp)
        # print(d)
        self.assertTrue(d.find('UTCTiming') > 0,
                        "Should find UTC-timing element")
        self.assertTrue(d.find('http://www.dashif.org/guidelines/low-latency-live-v5') > 0,
                        "Should find low-latency profile")
        self.assertTrue(d.find("<BaseURL>http://streamtest.eu/livesim/chunkdur_1/ato_7/testpic/</BaseURL>") > 0,
                        "Should not have availabilityTimeComplete here")
        self.assertTrue(d.find('availabilityTimeComplete="false"') > 0,
                        "Should find availabilityTimeComplete in SegmentTemplate")
        self.assertTrue(d.find('availabilityTimeOffset="7.000000"') > 0,
                        "Should find availabilityTimeOffset in SegmentTemplate")
        self.assertTrue(d.find('<ServiceDescription') > 0,
                        "Should find ServiceDescription in MPD")
        self.assertTrue(d.find('<ProducerReferenceTime') > 0,
                        "Should find ProducerReferenceTime in MPD")
