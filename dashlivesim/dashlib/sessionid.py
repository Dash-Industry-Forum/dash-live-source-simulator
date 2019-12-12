"""Session IDs to allow for tracing sessions."""

import random

MAX_NUMBER = 2**32 -1

def generate_session_id():
    "Generate a session ID as hex string."
    return "%08x" % random.randint(0, MAX_NUMBER)
