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

from dashlivesim.dashlib import scte35

testMessage = """\
<SpliceInfoSection ptsAdjustment="0" scte35:tier="4095">
<SpliceInsert spliceEventId="22" spliceEventCancelIndicator="false" outOfNetworkIndicator="false" uniqueProgramId="0" availNum="0" availsExpected="0" spliceImmediateFlag="false" >
<Program><SpliceTime ptsTime="1234"/></Program>
<BreakDuration autoReturn="true" duration="900000"/>
</SpliceInsert>
</SpliceInfoSection>"""

cancelMessage = """\
<SpliceInfoSection ptsAdjustment="0" scte35:tier="4095">
<SpliceInsert spliceEventId="22" spliceEventCancelIndicator="true">
</SpliceInsert>
</SpliceInfoSection>"""

class TestScte35(unittest.TestCase):

    def testScte35MessageData(self):
        ptsAdjustment = 0
        tier = 4095
        spliceEventId = 22
        spliceEventCancelIndicator = False
        outOfNetworkIndicator = False
        uniqueProgramId = 0
        availNum = 0
        availsExpected = 0
        spliceImmediateFlag = False
        ptsTime = 1234
        autoReturn = True
        duration = 900000
        message_data = scte35.create_scte35_insert_message(ptsAdjustment, tier, spliceEventId,
                                                           spliceEventCancelIndicator, outOfNetworkIndicator,
                                                           uniqueProgramId, availNum, availsExpected,
                                                           spliceImmediateFlag, ptsTime, autoReturn, duration)
        self.assertEqual(message_data, testMessage)


    def testScteCancelMessage(self):
        ptsAdjustment = 0
        tier = 4095
        spliceEventId = 22
        spliceEventCancelIndicator = True
        outOfNetworkIndicator = False
        uniqueProgramId = 0
        availNum = 0
        availsExpected = 0
        spliceImmediateFlag = False
        ptsTime = 1234
        autoReturn = True
        duration = 900000
        message_data = scte35.create_scte35_insert_message(ptsAdjustment, tier, spliceEventId,
                                                           spliceEventCancelIndicator, outOfNetworkIndicator,
                                                           uniqueProgramId, availNum, availsExpected,
                                                           spliceImmediateFlag, ptsTime, autoReturn, duration)
        self.assertEqual(message_data, cancelMessage)


class TestEmsgMessage(unittest.TestCase):

    def testEmsgMessage(self):
        timeScale = 90000
        presentationTimeOffset = 1000000000000
        presentationTime = 1000001800000
        duration = 900000
        messageId = 18
        spliceId = 13
        emsgBox = scte35.Scte35Emsg(timeScale, presentationTimeOffset, presentationTime, duration, messageId, spliceId)
        self.assertEqual(emsgBox.presentation_time_delta, presentationTime-presentationTimeOffset)
        self.assertEqual(emsgBox.emsg_id, messageId)

    def testNonAllowedTimescale(self):
        timeScale = 36000
        presentationTimeOffset = 1000000000000
        presentationTime = 1000001800000
        duration = 900000
        messageId = 18
        spliceId = 13
        self.assertRaises(scte35.Scte35Error, scte35.Scte35Emsg, timeScale, presentationTimeOffset, presentationTime,
                          duration, messageId, spliceId)
