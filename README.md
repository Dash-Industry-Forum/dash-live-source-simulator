# Time to move to livesim2!

This project is no longer maintained and new efforts are done in the <a href="https://github.com/Dash-Industry-Forum/livesim2">livesim2</a>
project instead.

The online service https://livesim.dashif.org will be stopped before the end of September and replaced by https://livesim2.dashif.org.

Please look at the new project and use <a href="https://github.com/Dash-Industry-Forum/livesim-content">livesim-content</a> to set
up your own test service.

# DASH-IF DASH Live Source Simulator

This software is intended as a reference that can be customized to provide a reference
for several use cases for live DASH distribution.

It uses VoD content in live profile as a start, and modifies the MPD and the media
segments to provide a live source. All modifications are made on the fly, which allows
for many different options as well as accurate timing testing.

The tool is written in Python3 and runs using using wsgi. There is a reference instance running
on AWS at https://livesim.dashif.org, but you can also run it on your own server.

Low-delay DASH is also supported.
