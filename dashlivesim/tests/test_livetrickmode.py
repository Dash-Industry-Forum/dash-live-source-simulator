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
        self.old_set_baseurl = mpdprocessor.SET_BASEURL
        mpdprocessor.SET_BASEURL = True

    def tearDown(self):
        mpdprocessor.SET_BASEURL = self.old_set_baseurl

    def testMpdPeriodReplaced(self):
	# Setup a simple live service with a single period.
	# Three adaptation sets.
	# Two video, one audio -> one video is a trick mode for another adaptation set.
	# We check if the essential property is set atleast in one of the adaptation sets. 
	# And, also whether the schemeIdUri is set correctly.
	urlParts = ['livesim', 'trickMode_1', 'testpic_2s', 'Manifest.mpd']
	dp = dash_proxy.DashProvider("10.4.247.98", urlParts, None, VOD_CONFIG_DIR, CONTENT_ROOT, now=10000)
	d = dp.handle_request()
	correct = 0
	xml = ET.fromstring(d)
	adaptationSetContainingEssentialProperty = []
	period = xml.findall('{urn:mpeg:dash:schema:mpd:2011}Period') 
	for adaptationSet in period[0].findall('{urn:mpeg:dash:schema:mpd:2011}AdaptationSet'):
	  essentialProperty = adaptationSet.find('{urn:mpeg:dash:schema:mpd:2011}EssentialProperty')
	  if essentialProperty is None:
	      continue
	  if(essentialProperty.attrib['schemeIdUri'] == "http://dashif.org/guidelines/trickmode"):
	      correct = 1
	self.assertTrue(correct == 1)
