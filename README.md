# DASH-IF DASH Live Source Simulator

This software is intended as a reference that can be customized to provide a reference
for several use cases for live DASH distribution.

It uses VoD content in live profile as a start, and modifies the MPD and the media
segments to provide a live source. All modifications are made on the fly, which allows
for many different options as well as accurate timing testing.

The tool is written in Python3 and runs using using wsgi. There is a reference instance running
on AWS at https://livesim.dashif.org, but you can also run it on your own server.

Low-delay DASH is also supported.
