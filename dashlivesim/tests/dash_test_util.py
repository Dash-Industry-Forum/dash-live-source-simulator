"""Utilities for testing."""

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

from os import unlink, makedirs
from os.path import join, abspath, dirname, exists
thisDir = abspath(dirname(__file__))
VOD_CONFIG_DIR = join(thisDir, "vod_cfg")
CONTENT_ROOT = thisDir
OUT_DIR = join(thisDir, "out_test")


def rm_outfile(filename):
    "Remove file from OUT_DIR if it exists."
    path = join(OUT_DIR, filename)
    if exists(path):
        unlink(path)


def write_data_to_outfile(data, filename):
    "Write data to a file in OUT_DIR."
    if not exists(OUT_DIR):
        makedirs(OUT_DIR)
    ofh = open(join(OUT_DIR, filename), "wb")
    ofh.write(data)
    ofh.close()


def findAllIndexes(needle, haystack):
    """Find the index for the beginning of each occurrence of ``needle`` in ``haystack``. Overlaps are allowed."""
    indexes = []
    last_index = haystack.find(needle)
    while -1 != last_index:
        indexes.append(last_index)
        last_index = haystack.find(needle, last_index + 1)
    return indexes
