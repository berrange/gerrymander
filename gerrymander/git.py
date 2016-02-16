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

import subprocess
try:
    # py3
    from urllib.parse import urlparse
except:
    # py2
    from urlparse import urlparse

def get_git_config(key):
    '''Read a git configuration value use "git config --get ..."'''
    try:
        val = subprocess.check_output([
            'git', 'config', '--get', key])
    except subprocess.CalledProcessError:
        return None

    if type(val) == bytes:
        return val.decode(encoding="utf-8")
    else:
        return val

def get_remote_info(remote):
    '''Read information for the named remote from the git configuration
    and return a (user, host, port) tuple.'''
    url = get_git_config('remote.%s.url' % remote)
    if not url:
        return (None, None, None)

    # only ssh urls make sense.  arguably this should support the
    # user@host:path syntax as well, but remotes configured using
    # "git review -s" will never look like that.
    if not url.startswith('ssh://'):
        return (None, None, None)

    url = urlparse(url)

    try:
        userhost, port = url.netloc.split(':')
    except ValueError:
        port = None
        userhost = url.netloc

    try:
        user, host = userhost.split('@')
    except ValueError:
        user = None
        host = url.netloc

    return (user, host, port)
