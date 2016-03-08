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

class TestXlinkPeriod(unittest.TestCase):

    def setUp(self):
        self.old_set_baseurl = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = True

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.old_set_baseurl

    def testMpdPeriodReplaced(self):
        " Check whether appropriate periods have been replaced by in .mpd file"
        collectresult = 1
        for k in [1, 2, 5, 10]:
            nr_period_per_hour = 10
            nr_xlink_periods_per_hour = k
            urlParts = ['livesim', 'periods_%s' %nr_period_per_hour, 'xlink_%s' %nr_xlink_periods_per_hour, 'testpic_2s', 'Manifest.mpd']
            dp = dash_proxy.DashProvider("10.4.247.98", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10000)
            d = dp.handle_request()
            period_id_all = findall('Period id="([^"]*)"', d)
            # Find all period ids in the .mpd file returned.
            # We will check whether the correct periods have been xlinked here.
            one_xlinks_for_how_many_periods =  nr_period_per_hour/nr_xlink_periods_per_hour
            period_id_xlinks = [int(x[1:]) % one_xlinks_for_how_many_periods for x in period_id_all]
            # All the period ids.
            # If there were any periods, that were not supposed to be there,
            # then one of the elements in period_id_xlinks would be zero.
            result = reduce(mul, period_id_xlinks, 1)
            collectresult = result * collectresult
        self.assertTrue(collectresult != 0)
