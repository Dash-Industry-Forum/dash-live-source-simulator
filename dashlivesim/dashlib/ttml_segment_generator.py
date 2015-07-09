"""Generate TTML init and media segments.

Start from template (which has timescale=1000)."""

from mp4filter import MP4Filter
from structops import uint32_to_str, str_to_uint32, uint64_to_str


TTML_MEDIA_TMPL = '\x00\x00\x00\x18stypmsdh\x00\x00\x00\x00msdhdash\x00\x00\x00`moof\x00\x00\x00\x10mfhd\x00\x00\
\x00\x00\x00\x00\x00\x01\x00\x00\x00Htraf\x00\x00\x00\x18tfhd\x00\x02\x00\x18\x00\x00\x00\x03\x00\x00\x03\xe8\x00\
\x00\x00\t\x00\x00\x00\x14tfdt\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x14trun\x00\x00\x00\
\x01\x00\x00\x00\x01\x00\x00\x00h\x00\x00\x00\x08mdat'

SAMPLE_TIME_SCALE = 1000 # This is the units for tfdt time and durations.
TRACK_ID = 3
# The init has sample_time_scale and trackID according to the values above
TTML_INIT = '\x00\x00\x00\x18ftypiso6\x00\x00\x00\x01isomdash\x00\x00\x02\x9dmoov\x00\x00\x00lmvhd\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc8\x00\x00\x00\x00\x00\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00@\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00(mvex\x00\x00\x00 trex\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x01\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x01trak\x00\x00\x00\\tkhd\x00\x00\x00\x07\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00@\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x9dmdia\x00\x00\x00 mdhd\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\xe8\x00\x00\x00\x00\x15\xc7\x00\x00\x00\x00\x00-hdlr\x00\x00\x00\x00\
\x00\x00\x00\x00subt\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00DASH-IF TTML\x00\x00\x00\x01Hminf\x00\x00\x00\x0c\
sthd\x00\x00\x00\x00\x00\x00\x00$dinf\x00\x00\x00\x1cdref\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x0curl \x00\x00\
\x00\x01\x00\x00\x01\x10stbl\x00\x00\x00\xc4stsd\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\xb4stpp\x00\x00\x00\x00\
\x00\x00\x00\x01http://www.w3.org/ns/ttml#parameter http://www.w3.org/ns/ttml http://www.w3.org/ns/ttml#styling http:\
//www.w3.org/ns/ttml#metadata urn:ebu:metadata urn:ebu:style\x00\x00\x00\x00\x00\x00\x10stts\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x10stsc\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x14stsz\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x10stco\x00\x00\x00\x00\x00\x00\x00\x00'


#EBU-TT-D sample
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
    </styling>
    <layout>
      <region xml:id="r0" tts:origin="15% 80%" tts:extent="70% 20%" tts:overflow="visible" tts:displayAlign="before"/>
    </layout>
  </head>
  <body tts:textAlign="center" style="s0">
    <div region="r0">
      <p xml:id="s0" begin="00:00:00.00" end="00:00:01.00" >
        <span style="s2">The time is 00:00:00</span>
      </p>
      <p xml:id="s1" begin="00:00:01.00" end="00:00:02.80">
        <span>The time is 00:00:01</span>
      </p>
    </div>
  </body>
</tt>
'''



class TtmlSegmentGeneratorError(Exception):
    "Error in TtmlSegmentGenerator."


class TtmlMediaFilter(MP4Filter):
    "Generate a TTML media segment with the limitation that there can only be one sample (<tt>)."

    def __init__(self, track_id, sequence_nr, sample_duration, tfdt_time, ttml_data):
        MP4Filter.__init__(self, data=TTML_MEDIA_TMPL)
        self.track_id = track_id
        self.sequence_nr = sequence_nr
        self.default_sample_duration = sample_duration
        self.default_sample_size = len(ttml_data)
        self.tfdt_time = tfdt_time
        self.ttml_data = ttml_data
        self.relevant_boxes = ['styp', 'moof', 'mdat', 'sidx']
        self.composite_boxes = ['moof', 'moof.traf']

    def filter_box(self, boxtype, data, file_pos, path=""):
        "Filter box or tree of boxes recursively."
        #pylint: disable=too-many-branches
        if path == "":
            path = boxtype
        else:
            path = "%s.%s" % (path, boxtype)

        output = ""

        #print "%d %s %d" % (len(self.output), boxtype, len(data))
        if path == "sidx":
                raise TtmlMediaFilter("SIDX presence not supported")
        elif path in self.composite_boxes:
            output += data[:8]
            pos = 8
            while pos < len(data):
                size, boxtype = self.check_box(data[pos:pos+8])
                output += self.filter_box(boxtype, data[pos:pos+size], file_pos+pos, path)
                pos += size
        elif path == "moof.mfhd":
            output += data[:12]
            output += uint32_to_str(self.sequence_nr)
        elif path == "moof.traf.tfhd":
            output += self.process_tfhd(data)
        elif path == "moof.traf.tfdt":
            output += self.process_tfdt(data)
        elif path == "mdat":
            output += self.process_mdat(data)
        else:
            output = data
        return output

    def process_tfhd(self, data):
        "Process a tfhd box and set trackID, defaultSampleDuration and defaultSampleSize"
        tf_flags = str_to_uint32(data[8:12]) & 0xffffff
        assert tf_flags == 0x020018, "Can only handle certain tf_flags combinations"
        output = data[:12]
        output += uint32_to_str(self.track_id)
        output += uint32_to_str(self.default_sample_duration)
        output += uint32_to_str(self.default_sample_size)
        return output

    def process_tfdt(self, data):
        "Process a tfdt box and set the baseMediaDecodeTime."
        version = ord(data[8])
        assert version == 1, "Can only handle tfdt version 1 (64-bit tfdt)."
        output = data[:12]
        output += uint64_to_str(self.tfdt_time)
        return output

    def process_mdat(self, data):
        "Make an mdat box with the right size to contain the one-and-only ttml sample."
        size = self.default_sample_size + 8
        return uint32_to_str(size) + 'mdat' + self.ttml_data


def create_segment(track_id, sequence_nr, sample_duration, tfdt_time, ttml_data):
    "Create a media segment."
    ttml_seg = TtmlMediaFilter(track_id, sequence_nr, sample_duration, tfdt_time, ttml_data)
    return ttml_seg.filter()