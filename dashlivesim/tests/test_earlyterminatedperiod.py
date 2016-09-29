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
import xml.etree.ElementTree as ET


class TestXlinkPeriod(unittest.TestCase):

    def setUp(self):
        self.old_set_baseurl_value = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = True

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.old_set_baseurl_value

    def testMpdPeriodReplaced(self):
        " Check whether appropriate periods have been replaced by in .mpd file"
        collectresult = 0
        for k in [1, 2, 5, 10, 20, 30]:
            nr_period_per_hour = 60
            nr_etp_periods_per_hour = k
            urlParts = ['livesim', 'periods_%s' %nr_period_per_hour, 'etp_%s' %nr_etp_periods_per_hour, 'testpic_2s',
                        'Manifest.mpd']
            dp = dash_proxy.DashProvider("10.4.247.98", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10000)
            d = dp.handle_request()
            xml = ET.fromstring(d)
            # Make the string as a xml document.
            periods_containing_duration_attribute = []
            # This array would contain all the period id that have duration attributes.
            # In the following, we will check if the correct period element have been assigned duration attributes.
            for child in xml.findall('{urn:mpeg:dash:schema:mpd:2011}Period'): # Collect all period elements first
                if child.attrib.has_key('duration'): # If the period element has the duration attribute.
                    periods_containing_duration_attribute.append(child.attrib['id'])
                    # Then collect its period id in this array
            one_etp_for_how_many_periods = nr_period_per_hour/nr_etp_periods_per_hour
            checker_array = [int(x[1:]) % one_etp_for_how_many_periods for x in periods_containing_duration_attribute]
            # In the above line, we check if each period id evaluates to zero or not.
            # Ideally, if everything worked well, then the checker array would be all zero.
            collectresult = collectresult + sum(checker_array)
            # Here, we keep collecting the sum of checker array. Even if one element evaluates to non zero values, then
            # the whole test will fail.
        self.assertTrue(collectresult == 0)