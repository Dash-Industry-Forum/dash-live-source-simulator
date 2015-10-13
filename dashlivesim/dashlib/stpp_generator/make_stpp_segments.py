"""Generator of TTML/stpp mp4 media segments with fixed duration according to a template."""

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

import os
from .stpp_creator import StppInitFilter, create_media_segment, TTML_TEMPLATE
from argparse import ArgumentParser
from jinja2 import Template

BODY_TEMPLATE = u'''
    <div region="r0">
      {% for p in paragraph %}
      <p xml:id="{{p.id}}" begin="{{p.begin}}" end="{{p.end}}" >
        <span style="s1">{{p.text}}</span>
      </p>
      {% endfor %}
    </div>
'''

"""
    <!--div region="r1">
      <p xml:id="{{r1_id}}" begin="{{r1_begin}}" end="{{r1_end}}" >
        <span style="s2">{{r1_text}}</span>
      </p>
    </div-->
"""

TTML_XML = TTML_TEMPLATE.format(BODY_TEMPLATE)


class SegmentCreator(object):
    "Creator of both init and media segments."
    def __init__(self, number_of_segments, segment_duration, resolution, segment_name_format,
                 language, trackid, output_path):
        self.number_of_segments = number_of_segments
        self.segment_duration = segment_duration
        self.segment_name_format = segment_name_format
        self.language = language
        self.trackid = trackid
        self.output_path = output_path
        self.resolution = resolution

    #pylint: disable=too-many-locals
    def create_segments(self):
        "Create init and media segments."
        print "Creating: %dx%d"%(self.number_of_segments, self.segment_duration)

        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_path):
            os.mkdir(self.output_path)

        # Create init segment
        init_segment_path = os.path.join(self.output_path, "init.mp4")
        with open(init_segment_path, 'wb') as iof:
            initfilter = StppInitFilter(self.language, self.trackid, self.resolution)
            initseg = initfilter.filter()
            iof.write(initseg)

        # Create jinja2 template
        ttml_template = Template(TTML_XML.strip())

        # Create media segments
        time = 0
        for seg_nr in range(1, self.number_of_segments + 1):
            media_segment_path = (os.path.join(self.output_path, self.segment_name_format)+".m4s") % (seg_nr)

            r1_start_time = self.create_time_string(time)
            r1_end_time = self.create_time_string(time + self.segment_duration)
            r1_text = "Segment: %d"%(seg_nr)
            # Create paragraph info
            pars = []
            for rel_time in range(0, self.segment_duration, self.resolution):
                start_time = self.create_time_string(time + rel_time)
                end_time = self.create_time_string(time + rel_time + self.resolution)

                id_str = "sub%05d"%(time+rel_time)

                text = '%s : %s'%(self.language, start_time)

                pars.append({'begin':start_time, 'end':end_time, 'id':id_str, 'text':text})

            ttml_data = ttml_template.render(paragraph=pars, r1_id="%010d"%(time), r1_begin=r1_start_time,
                                             r1_end=r1_end_time, r1_text=r1_text, lang=self.language)
            #print ttml_data.encode('utf-8')

            with open(media_segment_path, "wb") as mof:
                output = create_media_segment(self.trackid, seg_nr, self.segment_duration, time,
                                              ttml_data.encode('utf-8'))
                mof.write(output)

            time += self.segment_duration


    #pylint: disable=no-self-use
    def create_time_string(self, time_ms):
        "Create time string from number of milliseconds."
        hours, time_ms = divmod(time_ms, 3600000)
        minutes, time_ms = divmod(time_ms, 60000)
        seconds, milliseconds = divmod(time_ms, 1000)
        return "%02d:%02d:%02d.%03d"%(hours, minutes, seconds, milliseconds)


def main():
    "Parse command line and run script."
    parser = ArgumentParser()
    parser.add_argument("-d", "--segment_duration", dest="segment_duration", type=int,
                        help="duration of segment in ms", required=True)
    parser.add_argument("-n", "--number_of_segments", dest="number_of_segments", type=int,
                        help="number of segments to generate", required=True)
    parser.add_argument("-o", "--output_path", dest="output_path", type=str,
                        help="path to output folder", required=True)
    parser.add_argument("-f", "--segment_name_format", dest="segment_name_format", type=str,
                        help="format of media segment w/o extension (default %%d).", default="%d")
    parser.add_argument("-r", "--resolution", dest="resolution", type=int,
                        help="subtitle time stamp resolution (default = 1000)", default=1000)
    parser.add_argument("-l", "--language", dest="language", type=str, help="language (3 letters, default eng)",
                        default="eng")
    parser.add_argument("-t", "--trackid", dest="trackid", type=int, help="trackID (default 3)", default=3)
    args = parser.parse_args()
    output_path = os.path.abspath(args.output_path)
    seg_creator = SegmentCreator(args.number_of_segments, args.segment_duration, args.resolution,
                                 args.segment_name_format, args.language, args.trackid, output_path)
    seg_creator.create_segments()

if __name__ == "__main__":
    main()
