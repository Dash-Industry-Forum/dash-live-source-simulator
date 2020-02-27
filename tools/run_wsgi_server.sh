# Run a local mod_wsgi server
export PYTHONPATH=${PYTHONPATH}:..
python3 -m dashlivesim.mod_wsgi.mod_dashlivesim $*
