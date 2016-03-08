import unittest, sys

from dash_test_util import *
from dashlivesim.dashlib import dash_proxy
from dashlivesim.dashlib import mpdprocessor

def isMediaSegment(data):
    "Check if response is a segment."
    return type(data) == type("") and data[4:8] == "styp"

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
        d = dp.handle_request()
        write_data_to_outfile(d, testOutputFile)
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
        d = dp.handle_request()
        httpsIndexes = findAllIndexes("<BaseURL>https://", d)
        self.assertEqual(len(httpsIndexes), 2)

    def testCheckUpAndDownDependingOnTime(self):
        urlParts = ['livesim','all_1', 'baseurl_u40_d20', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=68)
        self.assertTrue(isMediaSegment(dp.handle_request()))
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=108)
        self.assertFalse(isMediaSegment(dp.handle_request()))

    def testCheckDowAndUpDependingOnTime(self):
        urlParts = ['livesim','all_1', 'baseurl_d40_u20', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=68)
        self.assertFalse(isMediaSegment(dp.handle_request()))
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=108)
        self.assertTrue(isMediaSegment(dp.handle_request()))

    def testCheckDowAndUpDependingOnTime30sPeriod(self):
        urlParts = ['livesim','all_1', 'baseurl_d20_u10', 'testpic', 'A1', '0.m4s']
        expected_results = [False, False, True, False, False, True]
        times = [7, 17, 27, 37, 47, 57]
        for (exp, now) in zip(expected_results, times):
            dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
            self.assertEqual(isMediaSegment(dp.handle_request()), exp, "Did not match for time %s" % now)

    def testCheckUpAndDownDependingOnTime30sPeriod(self):
        urlParts = ['livesim','all_1', 'baseurl_u20_d10', 'testpic', 'A1', '0.m4s']
        expected_results = [True, True, False, True, True, False]
        times = [7, 17, 27, 37, 47, 57]
        for (exp, now) in zip(expected_results, times):
            dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
            self.assertEqual(isMediaSegment(dp.handle_request()), exp, "Did not match for time %s" % now)

    def testOtherOrderOfOptions(self):
        urlParts = ['livesim', 'baseurl_u20_d10', 'all_1', 'testpic', 'A1', '0.m4s']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10)
        d = dp.handle_request()
        self.assertTrue(isMediaSegment(d), "Not a media segment, but %r" % d)
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=25)
        self.assertFalse(isMediaSegment(dp.handle_request()), "Is a media segment, but should not be")


