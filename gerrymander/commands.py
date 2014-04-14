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
from gerrymander.reports import ReportChanges
from gerrymander.reports import ReportToDoListMine
from gerrymander.reports import ReportToDoListOthers
from gerrymander.reports import ReportToDoListAnyones
from gerrymander.reports import ReportToDoListNoones

import getpass
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

    def has_option(self, section, name):
        return self.config.has_option(section, name)

    def get_option_string(self, section, name, defvalue=None):
        if not self.config.has_option(section, name):
            return defvalue
        return self.config.get(section, name)

    def get_option_list(self, section, name, defvalue=None):
        if not self.config.has_option(section, name):
            return defvalue
        value = self.config.get(section, name)
        return list(map(lambda x: x.strip(), value.split(",")))

    def get_option_bool(self, section, name, defvalue=None):
        if not self.config.has_option(section, name):
            return defvalue
        value = self.config.get(section, name).strip()
        if value.lower() in ["true", "yes"]:
            return True
        return False

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

    def get_organization_groups(self):
        if not self.config.has_option("organization", "groups"):
            return []
        value = self.config.get("organization", "groups")
        return list(map(lambda x: x.strip(), value.split(",")))

    def get_organization_teams(self):
        if not self.config.has_option("organization", "teams"):
            return []
        value = self.config.get("organization", "teams")
        return list(map(lambda x: x.strip(), value.split(",")))

    def get_organization_bots(self):
        if not self.config.has_option("organization", "bots"):
            return []
        value = self.config.get("organization", "bots")
        return list(map(lambda x: x.strip(), value.split(",")))

    def get_group_projects(self, groupname):
        section = "group-" + groupname
        if not self.config.has_option(section, "projects"):
            return []
        value = self.config.get(section, "projects")
        return list(map(lambda x: x.strip(), value.split(",")))

    def get_group_team_members(self, groupname, teamname):
        section = "group-" + groupname
        key = "team-" + teamname
        if not self.config.has_option(section, key):
            return []
        value = self.config.get(section, key)
        return list(map(lambda x: x.strip(), value.split(",")))


class Command(object):

    def __init__(self, name):
        self.name = name
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
        self.add_option("-z", "--profile",
                        help="Select command options set from config")

    def is_config_option_set(self, options, name):
        option = self.options[name]
        value = getattr(options, name)
        if getattr(options, name) == None:
            return False

        if option.action == "append":
            if len(getattr(options, name)) == 0:
                return False
        elif option.action == "store_true":
            if getattr(options, name) == False:
                return False

        return True

    def set_config_option(self, config, options, name):
        option = self.options[name]
        value = getattr(options, name)

        if self.is_config_option_set(options, name):
            return

        value = None
        section =  "command-" + self.name
        if options.profile is not None:
            altsection =  "command-" + self.name + "-" + options.profile
            if config.has_option(altsection, name):
                section = altsection
        if not config.has_option(section, name):
            return

        if option.action == "store_true":
            setattr(options, name, config.get_option_bool(section, name))
        elif option.action == "append":
            setattr(options, name, config.get_option_list(section, name))
        else:
            setattr(options, name, config.get_option_string(section, name))

    def set_config_options(self, config, options):
        for name in self.options.keys():
            self.set_config_option(config, options, name)

    def get_client(self, config, options):
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
        config = self.get_config(options)
        self.set_config_options(config, options)

        level = logging.WARNING
        if options.debug:
            level = logging.DEBUG
        elif options.quiet:
            level = logging.ERROR

        logging.basicConfig(level=level,
                            format='%(asctime)s %(levelname)s: %(message)s',
                            stream=sys.stderr)

        client = self.get_client(config, options)

        return self.run(config, client, options, args)


class CommandCaching(Command):

    def __init__(self, name):
        Command.__init__(self, name)

    def add_options(self):
        Command.add_options(self)
        self.add_option("--no-cache", action="store_true",
                        help="Disable use of gerrit query cache")
        self.add_option("--refresh", action="store_true",
                        help="Force refresh of the query cache")

    def get_client(self, config, options):
        if options.no_cache:
            return ClientLive(config.get_server_hostname(),
                              config.get_server_port(),
                              config.get_server_username(),
                              config.get_server_keyfile())
        else:
            return ClientCaching(config.get_server_hostname(),
                                 config.get_server_port(),
                                 config.get_server_username(),
                                 config.get_server_keyfile(),
                                 config.get_cache_directory(),
                                 config.get_cache_lifetime(),
                                 options.refresh)


class CommandWatch(Command):

    def __init__(self):
        Command.__init__(self, "watch")

    def run(self, config, client, options, args):
        watch = OperationWatch(client)

        def cb(event):
            print (str(event))

        return watch.run(cb)


class CommandReport(CommandCaching):

    def __init__(self, name):
        CommandCaching.__init__(self, name)

    def add_options(self):
        CommandCaching.add_options(self)

        self.add_option("-l", "--limit", default=None,
                        help="Limit to N results")

        self.add_option("--sort", default=None,
                        help="Set the sort field")
        self.add_option("--field", default=[],
                        action="append",
                        help="Display the named field")

    def get_report(self, config, client, options, args):
        raise NotImplementedError("subclass must override get_query")

    def run(self, config, client, options, args):
        report = self.get_report(config, client, options, args)

        limit = options.limit
        if limit is not None:
            limit = int(limit)

        if options.sort is not None:
            reverse = False
            offset = options.sort.find(":")
            if offset != -1:
                if options.sort[offset + 1:] == "rev":
                    reverse = True
                options.sort = options.sort[0:offset]
            report.set_sort_column(options.sort, reverse)

        if len(options.field) > 0:
            for col in report.get_columns():
                col.visible = False
            for key in options.field:
                name = key
                offset = name.find(":")
                truncate = None
                if offset != -1:
                    truncate = int(name[offset+1:])
                    name = name[0:offset]
                col = report.get_column(name)
                if col is None:
                    raise Exception("Unknown field '%s'" % name)
                if truncate is not None:
                    col.truncate = truncate
                col.visible = True

        table = report.get_table(limit=limit)
        print (table)


class CommandProject(CommandReport):

    def __init__(self, name):
        CommandReport.__init__(self, name)


    def add_options(self):
        CommandReport.add_options(self)

        self.add_option("-p", "--project", default=[],
                        action="append",
                        help="Gather information for project")

        self.add_option("-g", "--group", default=[],
                        action="append",
                        help="Gather information for project group")

        self.add_option("--all-groups", action="store_true",
                        help="Report on changes from all project groups")


    def get_projects(self, config, options, requireOne=False):
        count = 0
        if len(options.project) > 0:
            count = count + 1
        if len(options.group) > 0:
            count = count + 1
        if options.all_groups:
            count = count + 1

        if count > 1:
            raise Exception("--project, --group and --all-groups are mutually exclusive")
        if count == 0 and requireOne:
            raise Exception("One of --project, --group or --all-groups is required")

        if len(options.project) == 0:
            projects = []
            if options.all_groups:
                groups = config.get_organization_groups()
            else:
                groups = options.group

            for group in groups:
                projects.extend(config.get_group_projects(group))
            return projects
        else:
            return options.project


class CommandPatchReviewStats(CommandProject):

    def __init__(self):
        CommandProject.__init__(self, "patchreviewstats")
        self.teams = {}

    def get_report(self, config, client, options, args):
        return ReportPatchReviewStats(client,
                                      self.get_projects(config, options, True),
                                      self.teams)

    def run(self, config, client, options, args):
        if options.all_groups:
            groups = config.get_organization_groups()
        else:
            groups = options.group

        char = '*'
        teamchars = {}
        self.teams = {}
        for team in config.get_organization_teams():
            teamchars[team] = char
            self.teams[char] = []
            char = char + "*"

        for group in groups:
            teams = {}
            for team in config.get_organization_teams():
                users = config.get_group_team_members(group, team)
                self.teams[teamchars[team]].extend(users)

        return CommandReport.run(self, config, client, options, args)


class CommandChanges(CommandProject):

    def __init__(self):
        CommandProject.__init__(self, "changes")

    def add_options(self):
        CommandProject.add_options(self)

        self.add_option("--status", action="append", default=[],
                        help="Filter based on status")
        self.add_option("--reviewer", action="append", default=[],
                        help="Filter based on reviewer")
        self.add_option("--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option("--message", action="append", default=[],
                        help="Filter based on message")
        self.add_option("--owner", action="append", default=[],
                        help="Filter based on owner")
        self.add_option("--approval", action="append", default=[],
                        help="Filter based on approval")

    def get_report(self, config, client, options, args):
        return ReportChanges(client,
                             self.get_projects(config, options),
                             status=options.status,
                             reviewers=options.reviewer,
                             branches=options.branch,
                             messages=options.message,
                             owners=options.owner,
                             approvals=options.approval,
                             files=args)

class CommandToDoMine(CommandProject):

    def __init__(self):
        CommandProject.__init__(self, "todo-mine")


    def get_report(self, config, client, options, args):
        username = config.get_server_username()
        if username is None:
            username = getpass.getuser()

        return ReportToDoListMine(client,
                                  username=username,
                                  projects=self.get_projects(config, options))


class CommandToDoOthers(CommandProject):

    def __init__(self):
        CommandProject.__init__(self, "todo-others")

    def get_report(self, config, client, options, args):
        username = config.get_server_username()
        if username is None:
            username = getpass.getuser()

        return ReportToDoListOthers(client,
                                    username=username,
                                    projects=self.get_projects(config, options))


class CommandToDoAnyones(CommandProject):

    def __init__(self):
        CommandProject.__init__(self, "todo-anyones")

    def get_report(self, config, client, options, args):
        return ReportToDoListAnyones(client,
                                     bots=config.get_organization_bots(),
                                     projects=self.get_projects(config, options))


class CommandToDoNoones(CommandProject):

    def __init__(self):
        CommandProject.__init__(self, "todo-noones")

    def get_report(self, config, client, options, args):
        return ReportToDoListNoones(client,
                                    bots=config.get_organization_bots(),
                                    projects=self.get_projects(config, options))
