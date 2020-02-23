"""emsg box as defined in ISO_IEC_FDIS_23009-1_(E).pdf

aligned(8) class EventMessageBox extends FullBox('emsg', version = 0, flags = 0){
   string 			 scheme_id_uri;
   string            value;
   unsigned int(32)  timescale;
   unsigned int(32)  presentation_time_delta;
   unsigned int(32)  event_duration;
   unsigned int(32)  id;
   unsigned int(8)   message_data[];
   }
}
The strings are null-terminated.

One particular scheme_id_uri is defined for dash: "urn:mpeg:dash:event:2012"
For our own messages, we should use some other scheme_id_uri.
"""

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

from dashlivesim.dashlib.structops import uint32_to_str

DASH_SCHEME = "urn:mpeg:dash:event:2012"

class Emsg(object):
    "EMSG MP4 box."

    def __init__(self, scheme_id_uri="", value="", timescale=1, presentation_time_delta=0, event_duration=0,
                 emsg_id=0, messagedata=""):
        self.scheme_id_uri = scheme_id_uri
        self.value = str(value)
        self.timescale = timescale
        self.presentation_time_delta = presentation_time_delta
        self.event_duration = event_duration
        self.emsg_id = emsg_id
        self.messagedata = messagedata

    def get_box(self):
        "Return emsg box as string."
        size = 12 + 4*4 + len(self.scheme_id_uri) + 1 + len(self.value) + 1 + len(self.messagedata)
        parts = []
        parts.append(uint32_to_str(size))
        parts.append(b"emsg")
        parts.append(b"\x00\x00\x00\x00")
        parts.append(self.scheme_id_uri.encode("utf-8") + b"\x00")
        parts.append(self.value + b"\x00")
        parts.append(uint32_to_str(self.timescale))
        parts.append(uint32_to_str(self.presentation_time_delta))
        parts.append(uint32_to_str(self.event_duration))
        parts.append(uint32_to_str(self.emsg_id))
        parts.append(self.messagedata.encode("utf-8"))
        return b"".join(parts)

    def get_messagedata(self):
        "Return the message data of the box."
        return self.messagedata

    def __str__(self):
        return "EMSG: %(scheme_id_uri)s %(value)s %(timescale)d %(presentation_time_delta)d %(event_duration)d" +\
        " %(emsg_id)d" % self.__dict__


def create_emsg(scheme_id_uri="", value="", timescale=1, presentation_time_delta=0, event_duration=0, emsg_id=0,
                message_data=""):
    "Create an emsg_box."
    emsg = Emsg(scheme_id_uri, value, timescale, presentation_time_delta, event_duration, emsg_id, message_data)
    return emsg.get_box()


def main():
    "Main function for testing."
    print("Writing file emsg.mp4")
    ofh = open("emsg.mp4", "wb")
    emsg = create_emsg(DASH_SCHEME, "1", 2000, 100, 345, 1, "xmldata")
    ofh.write(emsg)


if __name__ == "__main__":
    main()
