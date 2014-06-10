#
# Copyright (C) 2014 Red Hat, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os
import subprocess
import sys

pagerproc = None

def get_pager_env(name):
    if name not in os.environ:
        return None
    pager = os.environ[name]
    return pager

def get_pager():
    if not sys.stdout.isatty():
        return None

    pager = get_pager_env("GERRYMANDER_PAGER")
    if not pager:
        pager = get_pager_env("PAGER")
    if not pager:
        pager = "less"

    if pager == "cat":
        return None

    return pager

def stop_pager():
    global pagerproc
    if pagerproc is None:
        return

    sys.stdout.flush()
    sys.stderr.flush()
    os.close(1)
    pagerproc.stdin.close()
    pagerproc.wait()
    pagerproc = None

def start_pager():
    if not sys.stdout.isatty():
        return

    pager = get_pager()
    if not pager:
        return

    if "LESS" not in os.environ:
        os.environ["LESS"] = "FRSX"

    oldstdout = os.dup(1)
    global pagerproc
    pagerproc = subprocess.Popen([pager],
                                 stdin=subprocess.PIPE,
                                 stdout=oldstdout,
                                 close_fds=True)

    os.close(oldstdout)
    os.dup2(pagerproc.stdin.fileno(), 1)
