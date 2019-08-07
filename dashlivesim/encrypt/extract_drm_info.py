"Extract DRM data using the CPIX Python3 module."

import base64
import sys
import re
from collections import OrderedDict
import json

import cpix

PSSH_PATTERN = re.compile(b'<pssh[^>]+>([^<]+)</pssh>')

def extract_data(file_name):
    with open(file_name, 'rb') as ifh:
        xml = ifh.read()
    cp = cpix.parse(xml)
    cp_data = []
    for key in cp.content_keys:
        cek = key.cek
        kid = str(key.kid)
        cp_data[kid] = {'cek': cek,
                        'drm_data': OrderedDict()}
    for drm_system in cp.drm_systems:
        kid = str(drm_system.kid)
        system_id = str(drm_system.system_id)
        cp_data_b64 = drm_system.content_protection_data
        cp_data_parts = base64.b64decode(cp_data_b64).split(b'\r\n')
        pssh_data = cp_data_parts[0]
        mobj = PSSH_PATTERN.match(pssh_data)
        if mobj:
            pssh = mobj.groups(1)[0].decode('utf-8')
        cp_data[kid]['drm_data'][system_id] = pssh

    json_out = json.dumps(cp_data)
    print(json_out)

if __name__ == "__main__":
    extract_data(sys.argv[1])
