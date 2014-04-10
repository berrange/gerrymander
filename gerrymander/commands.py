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

from gerrymander.client import ClientLive
from gerrymander.client import ClientCaching
from gerrymander.operations import OperationWatch
from gerrymander.reports import ReportPatchReviewStats

import os
import logging
import sys
import optparse

try:
    import configparser
except:
    import ConfigParser as configparser

class CommandConfig(object):

    def __init__(self, filename):
        self.filename = filename
        self.config = configparser.ConfigParser()
        self.config.read([self.filename])

    def get_option(self, section, value, defvalue=None):
        if not self.config.has_option(section, value):
            return defvalue
        return self.config.get(section, value)

    def get_server_username(self):
        if not self.config.has_option("server", "username"):
            return None
        return self.config.get("server", "username")

    def get_server_hostname(self):
        if not self.config.has_option("server", "hostname"):
            return "review"
        return self.config.get("server", "hostname")

    def get_server_port(self):
        if not self.config.has_option("server", "port"):
            return 29418
        return self.config.get("server", "port")

    def get_server_keyfile(self):
        if not self.config.has_option("server", "keyfile"):
            return None
        return self.config.get("server", "keyfile")

    def get_cache_lifetime(self):
        if not self.config.has_option("cache", "lifetime"):
            return 86400
        return self.config.get("cache", "lifetime")

    def get_cache_directory(self):
        if not self.config.has_option("cache", "directory"):
            return os.path.expanduser("~/.gerrymander.d/cache")
        return self.config.get("cache", "directory")


class Command(object):

    def __init__(self, name, caching=False):
        self.name = name
        self.caching = caching
        self.parser = None
        self.options = {}

    def add_option(self, *args, **kwargs):
        option = self.parser.add_option(*args, **kwargs)
        self.options[option.dest] = option

    def add_options(self):
        self.parser = optparse.OptionParser()
        self.add_option("-c", "--config", default=os.path.expanduser("~/.gerrymander"),
                        help=("Override config file (default %s)" %
                              os.path.expanduser("~/.gerrymander")))
        self.add_option("-d", "--debug",
                        help="Display debugging information",
                        action="store_true")
        self.add_option("-q", "--quiet",
                        help="Supress display of warnings",
                        action="store_true")

    def set_config_options(self, config, options):
        for name in self.options.keys():
            option = self.options[name]
            value = getattr(options, name)
            if value is None or (type(value) == list and len(value) == 0):
                section = "command:" + self.name
                value = config.get_option(section, name)
                setattr(options, name, value)

    def get_client(self, config):
        if self.caching:
            return ClientCaching(config.get_server_hostname(),
                                 config.get_server_port(),
                                 config.get_server_username(),
                                 config.get_server_keyfile(),
                                 config.get_cache_directory(),
                                 config.get_cache_lifetime())
        else:
            return ClientLive(config.get_server_hostname(),
                              config.get_server_port(),
                              config.get_server_username(),
                              config.get_server_keyfile())

    def get_config(self, options):
        return CommandConfig(options.config)

    def run(self, config, client, options, args):
        raise NotImplementedError("Subclass should override run method")

    def execute(self):
        if self.parser is None:
            self.add_options()
        options, args = self.parser.parse_args()
        level = logging.WARNING
        if options.debug:
            level = logging.DEBUG
        elif options.quiet:
            level = logging.ERROR

        logging.basicConfig(level=level,
                            format='%(asctime)s %(levelname)s: %(message)s',
                            stream=sys.stderr)

        config = self.get_config(options)

        self.set_config_options(config, options)

        client = self.get_client(config)

        return self.run(config, client, options, args)


class CommandWatch(Command):

    def __init__(self):
        Command.__init__(self, "watch")

    def run(self, config, client, options, args):
        watch = OperationWatch(client)

        def cb(event):
            print (str(event))

        return watch.run(cb)


class CommandReport(Command):

    def __init__(self, name):
        Command.__init__(self, name, caching=True)

    def add_options(self):
        Command.add_options(self)
        self.add_option("-l", "--limit", default=None,
                          help="Limit to N results")

        self.add_option("-p", "--project", default=[],
                          action="append",
                          help="Gather information for project")

        self.add_option("-g", "--group", default=[],
                          action="append",
                          help="Gather information for project group")

    def get_projects(self, config, options):
        if len(options.project) > 0 and len(options.group) > 0:
            raise Exception("--project and --group are mutually exclusive")

    def get_report(self, config, client, options, args):
        raise NotImplementedError("subclass must override get_query")

    def run(self, config, client, options, args):
        report = self.get_report(config, client, options, args)

        table = report.get_table(limit=int(options.limit))
        print (table)

class CommandPatchReviewStats(CommandReport):

    def __init__(self):
        CommandReport.__init__(self, "patchreviewstats")

    def get_report(self, config, client, options, args):
        return ReportPatchReviewStats(client,
                                      options.project)

    def run(self, config, client, options, args):
        if len(options.project) == 0:
            sys.stderr.write("At least one project is required\n")
            return 255
        return CommandReport.run(self, config, client, options, args)
