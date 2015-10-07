# Run a local mod_wsgi server
export PYTHONPATH=${PYTHONPATH}:..
python -m dashlivesim.mod_wsgi.mod_dashlivesim $*
