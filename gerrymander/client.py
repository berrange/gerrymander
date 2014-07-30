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
import os.path
import subprocess
import sys
import json
import hashlib
import time
import fcntl

LOG = logging.getLogger(__name__)

class ClientLive(object):

    def __init__(self, hostname="review", port=None, username=None, keyfile=None):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.keyfile = keyfile

    def _run_async(self, argv):

        def _preexec_fn():
            os.setpgrp()

        stdout = subprocess.PIPE
        stderr = subprocess.PIPE
        LOG.debug("Running cmd %s" % " ".join(argv))
        sp = subprocess.Popen(argv,
                              stdout=stdout,
                              stderr=stderr,
                              stdin=None,
                              preexec_fn=_preexec_fn)
        return sp

    def _build_argv(self, cmdargv):
        argv = ['ssh']
        argv.extend(["-T", "-o", "BatchMode=yes", "-e", "none"])
        if self.port:
            argv.extend(["-p", str(self.port)])
        if self.keyfile and os.path.isfile(self.keyfile):
            argv.extend(['-i', str(self.keyfile)])
        if self.username is not None:
            argv.extend(["%s@%s" % (self.username, self.hostname)])
        else:
            argv.extend([self.hostname])
        argv.extend(["gerrit"])
        argv.extend(cmdargv)
        return argv

    def _process(self, sp, argv, cb):
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
        if sp.returncode != 0:
            lines = []
            while True:
                line = sp.stderr.readline()
                if not line:
                    break
                lines.append(line.decode("UTF-8"))
            msg = "".join(lines)
            args = " ".join(argv)
            raise Exception("Error running command %s: %s" %
                            (args, msg))

    def run(self, cmdargv, cb):
        argv = self._build_argv(cmdargv)
        sp = self._run_async(argv)
        return self._process(sp, argv, cb)


class ClientCachingLock(object):
    def __init__(self, lockfile):
        self.lockfile = lockfile

    def __enter__(self):
        self.lockfh = open(self.lockfile, "w")
        fcntl.lockf(self.lockfh, fcntl.LOCK_EX)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            fcntl.lockf(self.lockfh, fcntl.LOCK_UN)
            self.lockfh.close()
            self.lockfh = None
        except:
            LOG.exception("could not release lock on %s" % self.lockfile)


class ClientCaching(ClientLive):

    def __init__(self, hostname="review", port=None, username=None, keyfile=None,
                 cachedir="cache", cachelifetime=86400, refresh=False):
        super(ClientCaching, self).__init__(hostname, port, username, keyfile)
        self.cachedir = cachedir
        self.cachelifetime = cachelifetime
        self.lastpurge = None
        self.refresh = refresh

        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)

    def _purge_cache_locked(self):
        now = time.time()
        if self.lastpurge is not None and (now - self.lastpurge) < 60 * 60:
            return
        self.lastpurge = now

        then = now - self.cachelifetime
        LOG.debug("Looking for files in %s older than %d" % (self.cachedir, then))
        for file in os.listdir(self.cachedir):
            if file == "lock":
                continue
            filepath = os.path.join(self.cachedir, file)
            mtime = os.path.getmtime(filepath)
            LOG.debug("File %s has time %d" % (filepath, mtime))
            if mtime < then:
                LOG.info("Purging outdated cache %s" % filepath)
                os.unlink(filepath)

    def _purge_cache(self):
        # XXX we really need to protect individual files
        # against deletion while they're being read
        lock = ClientCachingLock(os.path.join(self.cachedir, "lock"))
        LOG.debug("acquiring lock for cache")
        with lock as lock:
            self._purge_cache_locked()

    def run(self, cmdargv, cb):
        self._purge_cache()
        argv = self._build_argv(cmdargv)
        args = " ".join(argv)
        m = hashlib.sha256()
        m.update(args.encode("UTF-8"))
        LOG.debug("Finding cache for args '%s'" % args)
        file = self.cachedir + "/" + m.hexdigest() + ".json"
        if not os.path.exists(file) or self.refresh:
            sp = self._run_async(argv)
            try:
                with open(file, "wb") as f:
                    while True:
                        line = sp.stdout.readline()
                        if not line:
                            break
                        f.write(line)
            except:
                os.unlink(file)
                raise

            sp.wait()
            if sp.returncode != 0:
                os.unlink(file)
                lines = []
                while True:
                    line = sp.stderr.readline()
                    if not line:
                        break
                    lines.append(line.decode("UTF-8"))
                msg = "".join(lines)
                raise Exception("Error running command %s: %s" %
                                (args, msg))

        sp = self._run_async(["cat", file])
        self._process(sp, argv, cb)
