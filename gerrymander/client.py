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

import logging
import os
import subprocess
import sys
import json
import hashlib

LOG = logging.getLogger(__name__)

class ClientLive(object):

    def __init__(self, hostname="review", port=None, username=None, keyfile=None):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.keyfile = keyfile

    def _run_async(self, argv):
        stdout = subprocess.PIPE
        LOG.debug("Running cmd %s" % " ".join(argv))
        sp = subprocess.Popen(argv,
                              stdout=stdout,
                              stderr=sys.stderr,
                              stdin=None)
        return sp

    def _build_argv(self, cmdargv):
        argv = ['ssh']
        if self.username is not None:
            argv.extend(["-u", self.username])
        if self.port:
            argv.extend(["-p", str(self.port)])
        if self.keyfile and os.path.isfile(self.keyfile):
            argv.extend(['-i', str(self.keyfile)])
        argv.extend([self.hostname])
        argv.extend(["gerrit"])
        argv.extend(cmdargv)
        return argv

    def _process(self, sp, cb):
        while True:
            line = sp.stdout.readline()
            if not line:
                break
            try:
                dec = json.loads(line.decode("UTF-8"))
                if not isinstance(dec, (dict)):
                    raise TypeError("Expected decoded dict, not %s" % (type(dec)))
                cb(dec)
            except Exception:
                LOG.exception("Failure processing %s", line)

        sp.wait()
        return sp.returncode

    def run(self, cmdargv, cb):
        sp = self._run_async(self._build_argv(cmdargv))
        return self._process(sp, cb)


class ClientCaching(ClientLive):

    def __init__(self, hostname="review", port=None, username=None, keyfile=None,
                 cachedir="cache", cachelifetime=86400):
        ClientLive.__init__(self, hostname, port, username, keyfile)
        self.cachedir = cachedir

        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)

    def run(self, cmdargv, cb):
        argv = self._build_argv(cmdargv)
        args = " ".join(argv)
        m = hashlib.sha256()
        m.update(args.encode("UTF-8"))
        file = self.cachedir + "/" + m.hexdigest() + ".json"
        if not os.path.exists(file):
            sp = self._run_async(argv)
            with open(file, "wb") as f:
                while True:
                    line = sp.stdout.readline()
                    if not line:
                        break
                    f.write(line)
            sp.wait()
            if sp.returncode != 0:
                os.unlink(file)
                return sp.returncode

        sp = self._run_async(["cat", file])
        return self._process(sp, cb)
