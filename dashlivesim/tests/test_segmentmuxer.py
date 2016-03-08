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

from dash_test_util import *
from dashlivesim.dashlib import segmentmuxer

V1_INIT = join(CONTENT_ROOT, "testpic/V1/init.mp4")
A1_INIT = join(CONTENT_ROOT, "testpic/A1/init.mp4")
V1_1 = join(CONTENT_ROOT, "testpic/V1/1.m4s")
A1_1 = join(CONTENT_ROOT, "testpic/A1/1.m4s")

class TestInitMuxing(unittest.TestCase):

    def testInitMuxing(self):
        testOutputFile = "init_muxed.mp4"
        rm_outfile(testOutputFile)
        mi = segmentmuxer.MultiplexInits(V1_INIT, A1_INIT)
        muxed = mi.construct_muxed()
        write_data_to_outfile(muxed, testOutputFile)


class TestSegmentMuxing(unittest.TestCase):

    def testFragmentMuxing(self):
        testOutputFile = "1_fmux.mp4s"
        rm_outfile(testOutputFile)
        ml = segmentmuxer.MultiplexMediaSegments(V1_1, A1_1)
        fmux = ml.mux_on_fragment_level()
        write_data_to_outfile(fmux, testOutputFile)

    def testSampleMuxing(self):
        testOutputFile = "1_smux.m4s"
        rm_outfile(testOutputFile)
        ml = segmentmuxer.MultiplexMediaSegments(V1_1, A1_1)
        smux = ml.mux_on_sample_level()
        write_data_to_outfile(smux, testOutputFile)
