"""Filter MP4 files and produce modified versions.

The filter is streamlined for DASH or other content with one track per file.
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

from .structops import str_to_uint32


class MP4FilterError(BaseException):
    "Error in MP4Filter or subclass."


class MP4Filter(object):
    """Base class for filters.

    Call filter() to get a filtered version of the file."""

    # pylint: disable=no-self-use, unused-argument

    def __init__(self, filename=None, data=None):
        self.filename = filename
        if filename is not None:
            self.data = open(filename, "rb").read()
        else:
            self.data = data
        self.emsg = None
        self.output = ""
        self.relevant_boxes = [] # Boxes at top-level to filter
        #print "MP4Filter with %s" % filename

    def check_box(self, data):
        "Check the type of box starting at position pos."
        size = str_to_uint32(data[:4])
        boxtype = data[4:8]
        return (size, boxtype)

    def filter(self):
        "Top level box parsing. The lower-level parsing is done in self.filter_box(). "
        self.output = ""
        pos = 0
        while pos < len(self.data):
            size, boxtype = self.check_box(self.data[pos:pos+8])
            boxdata = self.data[pos:pos+size]
            if boxtype in self.relevant_boxes:
                self.output += self.filter_box(boxtype, boxdata, len(self.output))
            else:
                self.output += boxdata
            pos += size
        self.finalize()
        return self.output

    def filter_box(self, boxtype, boxdata, file_pos, path=""):
        "Function to be implemented in subclass. Add path element for each level."
        raise MP4FilterError("Not implemented")

    def finalize(self):
        "Do any final adjustments, if needed."
        pass
