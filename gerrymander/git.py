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
import urlparse

def get_git_config(key):
    '''Read a git configuration value use "git config --get ..."'''
    val = subprocess.check_output([
        'git', 'config', '--get', key])

    return val

def get_remote_info(remote):
    '''Read information for the named remote from the git configuration
    and return a (user, host, port) tuple.'''
    url = get_git_config('remote.%s.url' % remote)
    if not url:
        return

    # only ssh urls make sense.  arguably this should support the
    # user@host:path syntax as well, but remotes configured using
    # "git review -s" will never look like that.
    if not url.startswith('ssh://'):
        return

    url = urlparse.urlparse(url)
    
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
