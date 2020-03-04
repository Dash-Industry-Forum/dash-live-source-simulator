"""Encrypt segments using Bento4's mp4encrypt."""

import os
from os.path import join, basename, dirname
from shutil import copyfile
import base64
import json
from argparse import ArgumentParser

from dashlivesim.vodanalyzer.dashanalyzer import DashAnalyzer
from dashlivesim.encrypt.fix_media_segments import fix_segment

KEY = '+5f6+rqidg+YaZG/0IyQcA=='
IV  = '0101020304050607'
KIDGUUID = '3712a6d0-617e-43ca-b655-3475a2ac9135'

DRM_NAMES = {'edef8ba9-79d6-4ace-a3c8-27dcd51d21ed': 'Widevine',
             '9a04f079-9840-4286-ab92-e65be0885f95': 'MSPR 2.0'}

ENCRYPT_TEMPLATE = ("mp4encrypt --method MPEG-CENC --fragments-info %(init)s "
                    "--key %(track_id)d:%(key_hex)s:%(iv)s "
                    "--property %(track_id)d:KID:%(kid_hex)s "
                    "--global-option mpeg-cenc.iv-size-8:true "
                    "%(infile)s %(outfile)s")

INIT_ENC_TEMPLATE = ("mp4encrypt --method MPEG-CENC "
                    "--key %(track_id)d:%(key_hex)s:%(iv)s "
                    "--property %(track_id)d:KID:%(kid_hex)s "
                    "--global-option mpeg-cenc.iv-size-8:true "
                    "%(infile)s %(outfile)s")

CP_GEN_TEMPLATE = ('<ContentProtection '
                   'schemeIdUri="urn:mpeg:dash:mp4protection:2011" '
                   'value="cenc" '
                   'cenc:default_KID="%(kid)s" />\n')

CP_DRM_TEMPLATE = ('<ContentProtection '
                   'value = "%(name)s" '
                   'schemeIdUri = '
                   '"urn:uuid:%(system_id)s">\n'
                   '<cenc:pssh>%(pssh)s</cenc:pssh>\n'
                   '</ContentProtection>\n')


def generate_mpd_cp_part(key_data):
    parts = []
    parts.append(CP_GEN_TEMPLATE % key_data)
    for drm in key_data['drm_data']:
        drm['name'] = DRM_NAMES[drm['system_id']]
        parts.append(CP_DRM_TEMPLATE % drm)
    return "".join(parts)


def read_drm_info(infile):
    "Read drm_info in JSON format produced by extract_drm_info"
    with open(infile, 'rb') as ifh:
        json_data = json.load(ifh)
    return json_data


def get_kid_and_key(key_data):
    key = key_data['cek']
    kid = key_data['kid']
    kid_hex = kid.replace('-', '')
    return kid_hex, key


def print_mpd_data(key_data, drm_nr, seg_nr):
    print("#### MPD DATA %d segment=%d #####\n%s\n" %
          (drm_nr, seg_nr, generate_mpd_cp_part(key_data)))


def encrypt(in_manifest, out_dir, drm_data, rotation_interval, iv):
    "Encrypt a DASH asset by modifying the manifest and encrypting the segments."
    dash_analyzer = DashAnalyzer(in_manifest)
    dash_analyzer.initMedia()

    drm_nr = 0

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
                drm_nr = 1
                key_data = drm_data[drm_nr]
                kid_hex, key = get_kid_and_key(key_data)
                if not os.path.exists(out_seg_dir):
                    os.makedirs(out_seg_dir)
                in_init_path = rep_data['absInitPath']
                out_init_path = join(out_seg_dir, basename(init_path))
                encrypt_segment("",
                                in_init_path,
                                out_init_path,
                                track_id=2,
                                key=key,
                                kid_hex=kid_hex,
                                iv=iv,
                                template=INIT_ENC_TEMPLATE)

                for i in range(rep_data['firstNumber'],
                               rep_data['lastNumber'] + 1):
                    #if i > 20:  # TODO remove this
                    #    break
                    if i == rep_data['firstNumber']:
                        print_mpd_data(key_data, drm_nr, i)
                    if rotation_interval > 0:
                        rel_nr = i - rep_data['firstNumber']
                        old_drm_nr = drm_nr
                        new_drm_nr = rel_nr // rotation_interval
                        if new_drm_nr != old_drm_nr:
                            drm_nr = new_drm_nr
                            key_data = drm_data[drm_nr]
                            kid_hex, key = get_kid_and_key(key_data)
                            print_mpd_data(key_data, drm_nr, i)
                    in_seg_rel_path = rep_data['relMediaPath'] % i
                    in_seg_abs_path = rep_data['absMediaPath'] % i
                    out_seg_abs_path = join(out_dir, in_seg_rel_path)
                    out_seg_tmp_path = join(out_dir, 'tmp_out.m4s')
                    encrypt_segment(rep_data['absInitPath'],
                                    in_seg_abs_path,
                                    out_seg_tmp_path,
                                    track_id=2,
                                    key=key,
                                    kid_hex=kid_hex,
                                    iv=iv)
                    fix_segment(out_seg_tmp_path, out_seg_abs_path, kid_hex, 8)
                    os.unlink(out_seg_tmp_path)

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


def encrypt_segment(init_seg, in_seg, out_seg, track_id, key, kid_hex, iv,
                    template = ENCRYPT_TEMPLATE):
    key_hex = base64tohex(key)
    cmd = template % \
          {'init': init_seg,
           'track_id': track_id,
           'key_hex': key_hex,
           'iv': iv,
           'kid_hex': kid_hex,
           'infile': in_seg,
           'outfile': out_seg
          }
    os.system(cmd)


def base64tohex(b64str):
    "Translate from base64 to hex."
    decoded_str = base64.b64decode(b64str)
    return "".join(["%02x" % ord(c) for c in decoded_str])


def main():
    parser = ArgumentParser()
    parser.add_argument('in_manifest')
    parser.add_argument('out_dir')
    parser.add_argument('drm_file')
    parser.add_argument('--rot', type=int, default=0, help="Rotate every n "
                                                           "segments")

    args = parser.parse_args()
    drm_data = read_drm_info(args.drm_file)
    encrypt(args.in_manifest, args.out_dir, drm_data, args.rot, IV)


if __name__ == "__main__":
    main()
    #drm_data = read_drm_info(
    # '/Users/tobbe/proj/github/DashIF/dash-live-source'
    #              '-simulator/dashlivesim/encrypt/DrmData.json')
    #in_manifest = '/Users/tobbe/Sites/dash/vod/testpic_2s_2min/Manifest.mpd'
    #out_dir = '/Users/tobbe/Sites/dash/vod/testpic_2s_2min_enc'
    #encrypt(in_manifest, out_dir, drm_data, IV)
