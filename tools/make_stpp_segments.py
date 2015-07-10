import sys
import os
from ttml_segment_generator import *
from argparse import ArgumentParser
from jinja2 import Template

TTML_XML = u'''
<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns:ttp="http://www.w3.org/ns/ttml#parameter" xmlns="http://www.w3.org/ns/ttml"
    xmlns:tts="http://www.w3.org/ns/ttml#styling" xmlns:ttm="http://www.w3.org/ns/ttml#metadata"
    xmlns:ebuttm="urn:ebu:metadata" xmlns:ebutts="urn:ebu:style"
    xml:lang="en" xml:space="default"
    ttp:timeBase="media"
    ttp:cellResolution="32 15">
  <head>
    <metadata>
      <ttm:title>DASH-IF Live Simulator</ttm:title>
      <ebuttm:documentMetadata>
        <ebuttm:conformsToStandard>urn:ebu:distribution:2014-01</ebuttm:conformsToStandard>
        <ebuttm:authoredFrameRate>30</ebuttm:authoredFrameRate>
      </ebuttm:documentMetadata>
    </metadata>
    <styling>
      <style xml:id="s0" tts:fontStyle="normal" tts:fontFamily="sansSerif" tts:fontSize="100%" tts:lineHeight="normal"
      tts:color="#FFFFFF" tts:wrapOption="noWrap"/>
      <style xml:id="s1" tts:color="#00FF00" tts:backgroundColor="#000000" ebutts:linePadding="0.5c"/>
      <style xml:id="s2" tts:color="#ff0000" tts:backgroundColor="#000000" ebutts:linePadding="0.5c"/>
    </styling>
    <layout>
      <region xml:id="r0" tts:origin="15% 80%" tts:extent="70% 20%" tts:overflow="visible" tts:displayAlign="before"/>
      <region xml:id="r1" tts:origin="50% 20%" tts:extent="70% 20%" tts:overflow="visible" tts:displayAlign="before"/>
    </layout>
  </head>
  <body tts:textAlign="center" style="s0">
    <div region="r0">
      {% for p in paragraph %}
      <p xml:id="{{p.id}}" begin="{{p.begin}}" end="{{p.end}}" >
        <span style="s1">{{p.text}}</span>
      </p>
      {% endfor %}
    </div>
  </body>
</tt>
'''

"""
    <!--div region="r1">
      <p xml:id="{{r1_id}}" begin="{{r1_begin}}" end="{{r1_end}}" >
        <span style="s2">{{r1_text}}</span>
      </p>
    </div-->
"""

class SegmentCreator:
    def __init__(self, number_of_segments, segment_duration, resolution, segment_name_format, output_path):
        self.number_of_segments = number_of_segments
        self.segment_duration = segment_duration
        self.segment_name_format = segment_name_format
        self.output_path = output_path
        self.resolution = resolution

    def create_segments(self):
        print "Creating: %dx%d"%(self.number_of_segments, self.segment_duration)

        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_path):
            os.mkdir(self.output_path)

        # Create init segments
        init_segment_path = os.path.join(self.output_path, "init.mp4")
        with open(init_segment_path, 'wb') as iof:
            iof.write(TTML_INIT)

        # Create jinja2 template
        ttml_template = Template(TTML_XML.strip())

        # Create media segments
        time = 0
        for s in range(1, self.number_of_segments + 1):
            media_segment_path = (os.path.join(self.output_path, self.segment_name_format)+".m4s")%(s)

            r1_start_time = self.create_time_string(time)
            r1_end_time = self.create_time_string(time + self.segment_duration)
            r1_text = "Segment: %d"%(s)
            # Create paragraph info
            ps = []
            for d in range(0, self.segment_duration, self.resolution):
                start_time = self.create_time_string(time + d)
                end_time = self.create_time_string(time + d + self.resolution)

                id_str = "sub%05d"%(time+d)
                
                text = 'The time is: %s'%(start_time)

                ps.append({'begin':start_time, 'end':end_time, 'id':id_str, 'text':text})

            ttml_data = ttml_template.render(paragraph=ps, r1_id="%010d"%(time), r1_begin=r1_start_time, r1_end=r1_end_time,r1_text=r1_text)
            #print ttml_data.encode('utf-8')

            with open(media_segment_path, "wb") as mof:
                output = create_media_segment(TRACK_ID, s, self.segment_duration, time, ttml_data.encode('utf-8'))
                mof.write(output)

            time += self.segment_duration


    def create_time_string(self, t):
        h = t / 3600000
        t -= h * 3600000;
        m = t / 60000
        t -= m * 60000
        s = t / 1000
        t -= s * 1000
        ms = t

        return "%02d:%02d:%02d.%03d"%(h, m, s, ms)
            

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-d", "--segment_duration", dest="segment_duration", type=int, help="duration of segment in MS", required=True)
    parser.add_argument("-n", "--number_of_segments", dest="number_of_segments", type=int, help="number of segments to generate", required=True)
    parser.add_argument("-f", "--segment_name_format", dest="segment_name_format", type=str, help="format of segment name incl %%d for number", required=True)
    parser.add_argument("-o", "--output_path", dest="output_path", type=str, help="path to output folder", required=True)
    parser.add_argument("-r", "--resolution", dest="resolution", type=int, help="time stamp resolution, default 1000", default=1000)

    args = parser.parse_args()

    output_path = os.path.abspath(args.output_path)

    sc = SegmentCreator(args.number_of_segments, args.segment_duration, args.resolution, args.segment_name_format, output_path)

    sc.create_segments()
    
