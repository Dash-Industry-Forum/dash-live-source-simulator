"""SCTE-35 splice cues in emsg format.

 Follows the DASH-IF guidelines."""

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

from . import emsg

# The scheme_id_uri is a bit unsure. There is also a binary format, which may be preferred (...:2014:bin)
SCHEME_ID_URI = "urn:scte:scte35:2013:xml"
PID = 999
PROFILE = "http://dashif.org/guidelines/adin/app"

PTS_MOD = 2**33

def make_xml_bool(value):
    "Return a true or false string."
    return value and "true" or "false"

class Scte35Error(Exception):
    "Error in SCTE-35 context."


def create_scte35_insert_message(pts_adjustment, tier, splice_event_id, splice_event_cancel_indicator,
                                 out_of_network_indicator, unique_program_id, avail_num, avails_expected,
                                 splice_immediate_flag, pts_time, auto_return, duration):
    "Create the emsg message data for an SCTE-35 Insert Event."
    #pylint: disable=too-many-arguments, too-many-locals
    splice_insert_attribs = {'spliceEventId' : splice_event_id,
                             'spliceEventCancelIndicator' : make_xml_bool(splice_event_cancel_indicator),
                             'outOfNetworkIndicator' : make_xml_bool(out_of_network_indicator),
                             'uniqueProgramId' : unique_program_id,
                             'availNum' : avail_num,
                             'availsExpected' : avails_expected,
                             'spliceImmediateFlag' : make_xml_bool(splice_immediate_flag)}
    splice_insert_attr_keys = ('spliceEventId', 'spliceEventCancelIndicator', 'outOfNetworkIndicator',
                               'uniqueProgramId', 'availNum', 'availsExpected', 'spliceImmediateFlag')
    splice_event_cancel_indicator = make_xml_bool(splice_event_cancel_indicator)
    splice_immediate_flag = make_xml_bool(splice_immediate_flag)
    lines = []
    lines.append('<SpliceInfoSection ptsAdjustment="%s" scte35:tier="%s">' % (pts_adjustment, tier))
    if splice_event_cancel_indicator == "false":
        attributes = " ".join(['%s="%s"' % (k, splice_insert_attribs[k]) for k in splice_insert_attr_keys])
        lines.append('<SpliceInsert %s >' % attributes)
        if splice_immediate_flag == "false":
            lines.append('<Program><SpliceTime ptsTime="%s"/></Program>' % pts_time)
        if duration:
            lines.append('<BreakDuration autoReturn="%s" duration="%s"/>' % (make_xml_bool(auto_return), duration))
    else:
        lines.append('<SpliceInsert spliceEventId="%s" spliceEventCancelIndicator="%s">'
                     % (splice_event_id, splice_event_cancel_indicator))
    lines.append("</SpliceInsert>")
    lines.append("</SpliceInfoSection>")
    return "\n".join(lines)


class Scte35Emsg(emsg.Emsg):
    "Class providing an SCTE-35 Insert EMSG box."

    def __init__(self, timescale, presentation_time_offset, presentation_time, duration, message_id, splice_id):
        #pylint: disable=too-many-locals
        if timescale != 90000:
            raise Scte35Error("Only supports timescale=90000")
        presentation_time_delta = presentation_time - presentation_time_offset
        pts_adjustment = 0
        tier = 4095
        splice_event_id = splice_id
        splice_event_cancel_indicator = False
        out_of_network_indicator = False
        unique_program_id = 0
        avail_num = 0
        avails_expected = 0
        splice_immediate_flag = False
        pts_time = presentation_time % PTS_MOD
        auto_return = True
        message_data = create_scte35_insert_message(pts_adjustment, tier, splice_event_id,
                                                    splice_event_cancel_indicator, out_of_network_indicator,
                                                    unique_program_id, avail_num, avails_expected,
                                                    splice_immediate_flag, pts_time, auto_return, duration)
        emsg.Emsg.__init__(self, SCHEME_ID_URI, PID, timescale, presentation_time_delta, duration,
                           message_id, message_data)


def create_scte35_emsg(timescale, presentation_time_offset, presentation_time, duration, message_id, splice_id):
    "Create the Emsg DASH box for SCTE35 splice_insert."
    scte35emsg = Scte35Emsg(timescale, presentation_time_offset, presentation_time, duration, message_id, splice_id)
    return scte35emsg.get_box()

