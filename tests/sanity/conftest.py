# The sanity run is not part of the test suite: it runs on request
# (python tests/sanity/sanity.py run), and its working folder holds other
# projects' clones, tests included. Nothing here is for pytest to collect.
collect_ignore_glob = ["*"]
