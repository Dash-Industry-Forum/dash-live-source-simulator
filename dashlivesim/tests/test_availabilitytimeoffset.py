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
from dashlivesim.dashlib import dash_proxy
from dashlivesim.dashlib import mpdprocessor

def isMediaSegment(data):
    "Check if response is a segment."
    return type(data) == type("") and data[4:8] == "styp"

class TestMPDwithATO(unittest.TestCase):
    "Test of MPDs with availability offset. Note that BASEURL must be set."

    def setUp(self):
        self.oldBaseUrlState = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = True

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.oldBaseUrlState

    def testMpdGeneration(self):
        "Check if availabilityTimeOffset is added correctly to the MPD file."
        testOutputFile = "ato.mpd"
        rm_outfile(testOutputFile)
        urlParts = ['livesim', 'ato_30', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        write_data_to_outfile(d, testOutputFile)
        self.assertEqual(d.find('availabilityTimeOffset="30')-d.find('<BaseURL'), len('<BaseURL')+1)

    def testMpdGenerationHttps(self):
        "Check if availabilityTimeOffset works with https"
        urlParts = ['livesim', 'ato_2.5', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0,
                                     is_https=True)
        d = dp.handle_request()
        self.assertEqual(d.find('availabilityTimeOffset="2.5')-d.find('<BaseURL'), len('<BaseURL')+1)

    def testMpdGenerationInf(self):
        "Check if availabilityTimeOffset works with https"
        urlParts = ['livesim', 'ato_inf', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertEqual(d.find('availabilityTimeOffset="INF')-d.find('<BaseURL'), len('<BaseURL')+1)

    def testMpdAtoSettings(self):
        "availabilityTimeOffset shouldn't appear if the setting is invalid"
        urlParts = ['livesim', 'ato_0', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertTrue(d.find('availabilityTimeOffset') < 0)

        urlParts = ['livesim', 'ato_-10', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertTrue(d.find('availabilityTimeOffset') < 0)

        urlParts = ['livesim', 'ato_aa', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertTrue(d.find('availabilityTimeOffset') < 0)

    def testCheckAvailabilityTime(self):
        "Check if timing is correct with availabilityTimeOffset."
        urlParts = ['livesim', 'start_60', 'ato_30', 'testpic', 'A1', '0.m4s']
        expected_results = [False, True, True] #should be available from 60+6-30=36s(default segment duration is 6s)
        times = [28, 38, 48]
        for (exp, now) in zip(expected_results, times):
            dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
            self.assertEqual(isMediaSegment(dp.handle_request()), exp, "Did not match for time %s" % now)

    def testCheckAvailabilityTimeFractional(self):
        "Check if timing with fractional seconds is correct with availabilityTimeOffset."
        urlParts = ['livesim', 'start_60', 'ato_1.5', 'testpic', 'A1', '0.m4s']
        expected_results = [False, True, True] #should be available from 60+6-1.5=64.5s(default segment duration is 6s)
        times = [64.3, 64.6, 64.9]
        for (exp, now) in zip(expected_results, times):
            dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
            self.assertEqual(isMediaSegment(dp.handle_request()), exp, "Did not match for time %s" % now)

    def testCheckAvailabilityTimeInf(self):
        "Check if timing with fractional seconds is correct with availabilityTimeOffset."
        urlParts = ['livesim', 'start_60', 'ato_inf', 'testpic', 'A1', '0.m4s']
        expected_results = [False, True, True] #should be available from 60s(AST)
        times = [59, 60, 61]
        for (exp, now) in zip(expected_results, times):
            dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=now)
            self.assertEqual(isMediaSegment(dp.handle_request()), exp, "Did not match for time %s" % now)
