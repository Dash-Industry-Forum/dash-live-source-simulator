import unittest

from dashlivesim.tests.dash_test_util import VOD_CONFIG_DIR, CONTENT_ROOT
from dashlivesim.tests.dash_test_util import rm_outfile, write_data_to_outfile, findAllIndexes

from dashlivesim.dashlib import dash_proxy, mpd_proxy
from dashlivesim.dashlib import mpdprocessor


def isMediaSegment(data):
    "Check if response is a segment."
    return isinstance(data, bytes) and data[4:8] == b"styp"


class TestMultipleBaseUrls(unittest.TestCase):
    "Test of redundant baseURLs with failing availability. Note that BASEURL must be set."

    def setUp(self):
        self.oldBaseUrlState = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = True

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.oldBaseUrlState

    def testMpdGeneration(self):
        testOutputFile = "MultiURL.mpd"
        rm_outfile(testOutputFile)
        urlParts = ['livesim', 'baseurl_u40_d20', 'baseurl_d40_u20', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = mpd_proxy.get_mpd(dp)
        write_data_to_outfile(d.encode('utf-8'), testOutputFile)
        baseURLindexes = findAllIndexes("<BaseURL>", d)
        ud_indexes = findAllIndexes("baseurl_u40_d20", d)
        du_indexes = findAllIndexes("baseurl_d40_u20", d)
        self.assertEqual(len(baseURLindexes), 2)
        self.assertEqual(len(ud_indexes), 1)
        self.assertEqual(len(du_indexes), 1)

    def testMpdGenerationHttps(self):
        urlParts = ['livesim', 'baseurl_u40_d20', 'baseurl_d40_u20', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0,
                                     is_https=True)
        d = mpd_proxy.get_mpd(dp)
        httpsIndexes = findAllIndexes("<BaseURL>https://", d)
        self.assertEqual(len(httpsIndexes), 2)

    def testCheckUpAndDownDependingOnTime(self):
        urlParts = ['livesim', 'ato_inf', 'baseurl_u40_d20', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=68)
        self.assertTrue(isMediaSegment(dash_proxy.get_media(dp)))
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=108)
        self.assertFalse(isMediaSegment(dash_proxy.get_media(dp)))

    def testCheckDowAndUpDependingOnTime(self):
        urlParts = ['livesim', 'ato_inf', 'baseurl_d40_u20', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=68)
        self.assertFalse(isMediaSegment(dash_proxy.get_media(dp)))
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=108)
        self.assertTrue(isMediaSegment(dash_proxy.get_media(dp)))

    def testCheckDowAndUpDependingOnTime30sPeriod(self):
        urlParts = ['livesim', 'ato_inf', 'baseurl_d20_u10', 'testpic', 'A1', '0.m4s']
        expected_results = [False, False, True, False, False, True]
        times = [7, 17, 27, 37, 47, 57]
        for (exp, now) in zip(expected_results, times):
            dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
            self.assertEqual(isMediaSegment(dash_proxy.get_media(dp)), exp, "Did not match for time %s" % now)

    def testCheckUpAndDownDependingOnTime30sPeriod(self):
        urlParts = ['livesim', 'ato_inf', 'baseurl_u20_d10', 'testpic', 'A1', '0.m4s']
        expected_results = [True, True, False, True, True, False]
        times = [7, 17, 27, 37, 47, 57]
        for (exp, now) in zip(expected_results, times):
            dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
            self.assertEqual(isMediaSegment(dash_proxy.get_media(dp)), exp, "Did not match for time %s" % now)

    def testOtherOrderOfOptions(self):
        urlParts = ['livesim', 'baseurl_u20_d10', 'ato_inf', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10)
        d = dash_proxy.get_media(dp)
        self.assertTrue(isMediaSegment(d), "Not a media segment, but %r" % d)
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=25)
        self.assertFalse(isMediaSegment(dash_proxy.get_media(dp)), "Is a media segment, but should not be")
