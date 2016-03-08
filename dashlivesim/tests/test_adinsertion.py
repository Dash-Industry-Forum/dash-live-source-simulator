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
from re import findall
from operator import mul
from dashlivesim.dashlib import mpdprocessor
import xml.etree.ElementTree as ET


class TestXlinkPeriod(unittest.TestCase):

    def setUp(self):
        self.old_set_baseurl_value = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = True

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.old_set_baseurl_value

    def testMpdPeriodReplaced(self):
        " Check whether before every xlink period, duration attribute has been inserted"
        collect_result = []
        urlParts = ['livesim', 'periods_60', 'xlink_30', 'insertad_1', 'testpic_2s', 'Manifest.mpd']
        dp = dash_proxy.DashProvider("10.4.247.98", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10000)
        d = dp.handle_request()
        xml = ET.fromstring(d)
        # Make the string as a xml document.
        # In the following, we will check if for every period before every xlink period, duration attribute has been
        # added or not.
        prev_child = []
        for child in xml.findall('{urn:mpeg:dash:schema:mpd:2011}Period'): # Collect all period elements first
            if child.attrib.has_key('{http://www.w3.org/1999/xlink}actuate'): # If the period element has the duration attribute.
                collect_result.append(prev_child.attrib.has_key('duration')) # Then collect its period id in this
            prev_child = child
        # Ideally, at the periods should have a duration attribute, if no then the test fails.
        self.assertTrue((False in collect_result) == False)
