"""Encrypt segments using Bento4's mp4encrypt."""

import os
from os.path import join, basename, dirname
from shutil import copyfile
import base64

from dashlivesim.vodanalyzer.dashanalyzer import DashAnalyzer

KEY = '+5f6+rqidg+YaZG/0IyQcA=='
IV  = '0101020304050607'
KIDGUUID = '3712a6d0-617e-43ca-b655-3475a2ac9135'
KID_HEX = '3712a6d0617e43cab6553475a2ac9135'

ENCRYPT_TEMPLATE = ("mp4encrypt --method MPEG-CENC --fragments-info %(init)s "
                   "--key %(track_id)d:%(key_hex)s:%(iv)s "
                   "--property %(track_id)d:KID:%(kid_hex)s "
                   "--global-option mpeg-cenc.iv-size-8:true "
                   "%(infile)s %(outfile)s")

INIT_ENC_EMPLATE = ("mp4encrypt --method MPEG-CENC "
                   "--key %(track_id)d:%(key_hex)s:%(iv)s "
                   "--property %(track_id)d:KID:%(kid_hex)s "
                   "--global-option mpeg-cenc.iv-size-8:true "
                   "%(infile)s %(outfile)s")


def encrypt(in_manifest, out_dir, key, iv):
    "Encrypt a DASH asset by modifying the manifest and encrypting the segments."
    dash_analyzer = DashAnalyzer(in_manifest)
    dash_analyzer.initMedia()

    adaptation_sets = dash_analyzer.mpdProcessor.adaptation_sets
    for aset in adaptation_sets:
        content_type = aset.content_type
        if content_type == 'video':
            reps_data = dash_analyzer.as_data[content_type]
            for rep in aset.representations:
                for r in reps_data['reps']:
                    if r['representation'] == rep:
                        rep_data = r
                        break
                else:
                    raise ValueError("No representation found")
                init_path = rep_data['relInitPath']
                out_seg_dir = join(out_dir, dirname(init_path))
                if not os.path.exists(out_seg_dir):
                    os.makedirs(out_seg_dir)
                in_init_path = rep_data['absInitPath']
                out_init_path = join(out_seg_dir, basename(init_path))
                encrypt_segment("",
                                in_init_path,
                                out_init_path,
                                track_id=2,
                                key=key,
                                iv=iv,
                                template=INIT_ENC_EMPLATE)

                for i in range(rep_data['firstNumber'],
                               rep_data['lastNumber']):
                    in_seg_rel_path = rep_data['relMediaPath'] % i
                    in_seg_abs_path = rep_data['absMediaPath'] % i
                    out_seg_abs_path = join(out_dir, in_seg_rel_path)
                    encrypt_segment(rep_data['absInitPath'],
                                    in_seg_abs_path,
                                    out_seg_abs_path,
                                    track_id=2,
                                    key=key,
                                    iv=iv)
        else:
            reps_data = dash_analyzer.as_data[content_type]
            for rep in aset.representations:
                for r in reps_data['reps']:
                    if r['representation'] == rep:
                        rep_data = r
                        break
                else:
                    raise ValueError("No representation found")
                init_path = rep_data['relInitPath']
                out_seg_dir = join(out_dir, dirname(init_path))
                if not os.path.exists(out_seg_dir):
                    os.makedirs(out_seg_dir)
                out_init_name = join(out_seg_dir, basename(init_path))
                copyfile(rep_data['absInitPath'], out_init_name)
                for i in range(rep_data['firstNumber'],
                               rep_data['lastNumber']):
                    in_seg_rel_path = rep_data['relMediaPath'] % i
                    in_seg_abs_path = rep_data['absMediaPath'] % i
                    out_seg_abs_path = join(out_dir, in_seg_rel_path)
                    copyfile(in_seg_abs_path, out_seg_abs_path)


def encrypt_segment(init_seg, in_seg, out_seg, track_id, key, iv,
                    template = ENCRYPT_TEMPLATE):
    key_hex = base64tohex(key)
    cmd = template % \
          {'init': init_seg,
           'track_id': track_id,
           'key_hex': key_hex,
           'iv': iv,
           'kid_hex': KID_HEX,
           'infile': in_seg,
           'outfile': out_seg
          }
    os.system(cmd)

def base64tohex(b64str):
    "Translate from base64 to hex."
    decoded_str = base64.b64decode(b64str)
    return "".join(["%02x" % ord(c) for c in decoded_str])

if __name__ == "__main__":
    in_manifest = '/Users/tobbe/Sites/dash/vod/testpic_2s_2min/Manifest.mpd'
    out_dir = '/Users/tobbe/Sites/dash/vod/testpic_2s_2min_enc'
    encrypt(in_manifest, out_dir, KEY, IV)
