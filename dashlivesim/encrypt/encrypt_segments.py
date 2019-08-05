"""Encrypt segments using Bento4's mp4encrypt."""

import os
from os.path import join, basename, dirname
from shutil import copyfile

from dashlivesim.vodanalyzer.dashanalyzer import DashAnalyzer

KEY = 'B5910D78782E8731F548ACB8381FB9D3'
IV  = '010102030405060708090a0b0c0d0e0f'
KID = '000102030405060708090A0B0C0D0E0F'

ENCRYPT_TEMPLATE = "mp4encrypt --method MPEG-CENC --fragments-info %(init)s --key %(track_id)d:%(key)s:%(iv)s %(infile)s %(outfile)s"


def encrypt(in_manifest, out_dir, key, psshs):
    "Encrypt a DASH asset by modifying the manifest and encrypting the segments."
    dash_analyzer = DashAnalyzer(in_manifest)
    dash_analyzer.initMedia()

    in_dir = os.path.dirname(in_manifest)

    adaptation_sets = dash_analyzer.mpdProcessor.adaptation_sets
    for aset in adaptation_sets:
        if aset.content_type == 'video':
            for rep in aset.representations:
                init_path = rep.initialization_path
                out_seg_dir = join(out_dir, dirname(init_path))
                if not os.path.exists(out_seg_dir):
                    os.makedirs(out_seg_dir)
                out_init_name = join(out_seg_dir, basename(init_path))
                abs_init_path = join(in_dir, init_path)
                copyfile(abs_init_path, out_init_name)
                for i in range(1, 21):
                    in_seg_rel = rep.get_media_path(str(i))
                    in_seg = join(in_dir, in_seg_rel)
                    out_seg = join(out_dir, in_seg_rel)
                    encrypt_segment(abs_init_path,
                                    in_seg,
                                    out_seg,
                                    track_id=2,
                                    key=KEY,
                                    iv=IV)


def encrypt_segment(init_seg, in_seg, out_seg, track_id, key, iv):
    cmd = ENCRYPT_TEMPLATE % \
          {'init': init_seg,
           'track_id': track_id,
           'key': key,
           'iv': iv,
           'infile': in_seg,
           'outfile': out_seg
          }
    os.system(cmd)


if __name__ == "__main__":
    in_manifest = '/Users/tobbe/Sites/dash/vod/testpic_2s/Manifest.mpd'
    out_dir = '/Users/tobbe/Sites/dash/vod/testpic_2s_enc'
    encrypt(in_manifest, out_dir, '', '')
