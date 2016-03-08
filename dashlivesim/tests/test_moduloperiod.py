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
from dashlivesim.dashlib.moduloperiod import ModuloPeriod


class TestModuloCalculations(unittest.TestCase):

    def testMiddlePeriod(self):
        mp = ModuloPeriod(10, 2000)
        self.assertEqual(mp._minimum_update_period, 30)
        self.assertEqual(mp._availability_start_time, 1800)
        self.assertEqual(mp._media_presentation_duration, 360)
        self.assertEqual(mp._availability_end_time, 2190)

    def testEndOfMediaInPeriod(self):
        mp = ModuloPeriod(5, 540)
        self.assertEqual(mp._minimum_update_period, 15)
        self.assertEqual(mp._availability_start_time, 300)
        self.assertEqual(mp._media_presentation_duration, 240)
        self.assertEqual(mp._availability_end_time, 555)
        self.assertEqual(mp.compare_with_last_segment(269,2),0)

    def testFuturePeriod(self):
        mp = ModuloPeriod(5, 575)
        self.assertEqual(mp._minimum_update_period, 15)
        self.assertEqual(mp._availability_start_time, 600)
        self.assertEqual(mp._media_presentation_duration, 60)
        self.assertEqual(mp._availability_end_time, 675)
