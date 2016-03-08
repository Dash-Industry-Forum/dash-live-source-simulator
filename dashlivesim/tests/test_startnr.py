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

from dashlivesim.dashlib import dash_proxy

from dash_test_util import *

class TestMpdChange(unittest.TestCase):
    "Test that MPD gets startNr changed in an appropriate way"

    def testMpdWithNormalStartNr(self):
        "Check that startNumber=0."
        urlParts = ['pdash', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertEqual(len(findAllIndexes('startNumber="0"', d)), 2)
        self.assertTrue(d.find('availabilityStartTime="1970-01-01T00:00:00Z"') > 0)

    def testMpdWitdStartNrIs111(self):
        "Check that startNumber=111."
        urlParts = ['pdash', 'snr_111', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertEqual(len(findAllIndexes('startNumber="111"', d)), 2)
        self.assertTrue(d.find('availabilityStartTime="1970-01-01T00:00:00Z"') > 0)

    def testMpdWithStartNrIs1(self):
        "Check that startNumber=1."
        urlParts = ['pdash', 'snr_1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertEqual(len(findAllIndexes('startNumber="1"', d)), 2)
        self.assertTrue(d.find('availabilityStartTime="1970-01-01T00:00:00Z"') > 0)

    def testMpdWithImplicitStartNr(self):
        "Check that startNumber is not present in MPD."
        urlParts = ['pdash', 'snr_-1', 'testpic', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("streamtest.eu", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=0)
        d = dp.handle_request()
        self.assertTrue(d.find('startNumber=') < 0) #
        self.assertTrue(d.find('availabilityStartTime="1970-01-01T00:00:00Z"') > 0)

# Could add tests to check availability time of segments depending on startNr
# Add test to check if segmentNumber and tfdt are OK depending on startNr.
# Just running the reference player with different values seems to show that it is working properly, though.
