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
from gerrymander.operations import OperationQuery
from gerrymander.operations import OperationWatch
from gerrymander.reports import ReportOutput
from gerrymander.reports import ReportPatchReviewStats
from gerrymander.reports import ReportPatchReviewRate
from gerrymander.reports import ReportOpenReviewStats
from gerrymander.reports import ReportChanges
from gerrymander.reports import ReportToDoListMine
from gerrymander.reports import ReportToDoListOthers
from gerrymander.reports import ReportToDoListAnyones
from gerrymander.reports import ReportToDoListNoones
from gerrymander.reports import ReportToDoListApprovable
from gerrymander.reports import ReportToDoListExpirable
from gerrymander.format import format_color
from gerrymander.model import ModelEventCommentAdd
from gerrymander.model import ModelEventPatchCreate
from gerrymander.model import ModelEventChangeMerge
from gerrymander.model import ModelEventChangeAbandon
from gerrymander.model import ModelEventChangeRestore
from gerrymander.model import ModelApproval
from gerrymander.pager import start_pager, stop_pager

import getpass
import os
import logging
import sys
import argparse
import textwrap

try:
    import configparser
except:
    import ConfigParser as configparser

class CommandConfig(object):

    def __init__(self, filename):
        self.filename = os.path.expanduser(filename)
        self.config = configparser.ConfigParser()
        self.config.read([self.filename])

    def has_option(self, section, name):
        return self.config.has_option(section, name)

    def get_option_string(self, section, name, defvalue=None):
        if not self.config.has_option(section, name):
            return defvalue
        return self.config.get(section, name)

    def get_option_int(self, section, name, defvalue=None):
        if not self.config.has_option(section, name):
            return defvalue
        return int(self.config.get(section, name))

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

    def get_cache_longlifetime(self):
        if not self.config.has_option("cache", "longlifetime"):
            return 86400
        return self.config.get("cache", "lifetime")

    def get_cache_shortlifetime(self):
        if not self.config.has_option("cache", "shortlifetime"):
            return 300
        return self.config.get("cache", "shortlifetime")

    def get_cache_directory(self):
        if not self.config.has_option("cache", "directory"):
            return os.path.expanduser("~/.gerrymander.d/cache")
        return os.path.expanduser(self.config.get("cache", "directory"))

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

    def get_command_aliases(self):
        if not self.config.has_option("commands", "aliases"):
            return []
        value = self.config.get("commands", "aliases")
        return list(map(lambda x: x.strip(), value.split(",")))

    def get_command_alias_basecmd(self, aliasname):
        section = "alias-" + aliasname
        return self.config.get(section, "basecmd")

    def get_command_alias_help(self, aliasname):
        section = "alias-" + aliasname
        return self.config.get(section, "help")


class Command(object):

    def __init__(self, name, help):
        super(Command, self).__init__()
        self.name = name
        self.help = help
        self.pager = True

    def add_option(self, parser, config, *args, **kwargs):
        if args[0][0:1] == "-":
            if args[0][0:2] == "--":
                name = args[0][2:]
            else:
                name = args[1][2:]
        else:
            name = args[0]

        section = "command-" + self.name
        if config.has_option(section, name):
            defvalue = kwargs["default"]
            if type(defvalue) == list:
                kwargs["default"] = config.get_option_list(section, name)
            elif type(defvalue) == int:
                kwargs["default"] = config.get_option_int(section, name)
            elif type(defvalue) == bool:
                kwargs["default"] = config.get_option_bool(section, name)
            else:
                kwargs["default"] = config.get_option_string(section, name)

        return parser.add_argument(*args, **kwargs)


    def add_options(self, parser, config):
        pass

    def get_client(self, config, options):
        return ClientLive(config.get_server_hostname(),
                          config.get_server_port(),
                          config.get_server_username(),
                          config.get_server_keyfile())

    def run(self, config, client, options):
        raise NotImplementedError("Subclass should override run method")

    def execute(self, config, options):
        if self.pager:
            start_pager()
        try:
            client = self.get_client(config, options)

            self.run(config, client, options)
        finally:
            if self.pager:
                stop_pager()


class CommandCaching(Command):

    def __init__(self, name, help):
        super(CommandCaching, self).__init__(name, help)
        self.longcache = False

    def set_long_cache(self, longcache):
        self.longcache = longcache

    def add_options(self, parser, config):
        super(CommandCaching, self).add_options(parser, config)
        self.add_option(parser, config,
                        "--no-cache", action="store_true",
                        help="Disable use of gerrit query cache")
        self.add_option(parser, config,
                        "--refresh", action="store_true",
                        help="Force refresh of the query cache")

    def get_client(self, config, options):
        if options.no_cache:
            return ClientLive(config.get_server_hostname(),
                              config.get_server_port(),
                              config.get_server_username(),
                              config.get_server_keyfile())
        else:
            if self.longcache:
                return ClientCaching(config.get_server_hostname(),
                                     config.get_server_port(),
                                     config.get_server_username(),
                                     config.get_server_keyfile(),
                                     os.path.join(config.get_cache_directory(), "long"),
                                     config.get_cache_longlifetime(),
                                     options.refresh)
            else:
                return ClientCaching(config.get_server_hostname(),
                                     config.get_server_port(),
                                     config.get_server_username(),
                                     config.get_server_keyfile(),
                                     os.path.join(config.get_cache_directory(), "short"),
                                     config.get_cache_shortlifetime(),
                                     options.refresh)


class CommandProject(Command):

    def __init__(self, name, help):
        super(CommandProject, self).__init__(name, help)


    def add_options(self, parser, config):
        super(CommandProject, self).add_options(parser, config)

        self.add_option(parser, config,
                        "-p", "--project", default=[],
                        action="append",
                        help="Gather information for project")

        self.add_option(parser, config,
                        "-g", "--group", default=[],
                        action="append",
                        help="Gather information for project group")

        self.add_option(parser, config,
                        "--all-groups", action="store_true",
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


class CommandWatch(CommandProject):

    def __init__(self, name="watch", help="Watch incoming changes"):
        super(CommandWatch, self).__init__(name, help)

        self.pager = False

    def add_options(self, parser, config):
        super(CommandWatch, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--color", default=False, action="store_true",
                        help="Use terminal color highlighting")
        self.add_option(parser, config,
                        "--all", default=False, action="store_true",
                        help="Don't filter list of comments to strip bots")

    @staticmethod
    def wrap_text(message, indent="", width=78):
        lines = textwrap.wrap(message, width)
        return "\n".join(map(lambda x: indent + x, lines))

    @staticmethod
    def format_comment(comment, user, usecolor):
        if comment == "":
            return
        print ("  %s (%s) wrote:" % (format_color(user.name,
                                                  usecolor,
                                                  styles=["bold"]),
                                     user.username))
        print ("")
        print (CommandComments.wrap_text(comment, "  "))

    @staticmethod
    def format_approvals(approvals):
        bits = []
        for approval in approvals:
            if approval.action == ModelApproval.ACTION_WORKFLOW and approval.value > 0:
                bits.append("+A")
            elif approval.action == ModelApproval.ACTION_REVIEWED:
                if approval.value > 0:
                    bits.append("R+" + str(approval.value))
                elif approval.value < 0:
                    bits.append("R" + str(approval.value))
                else:
                    bits.append("R=0")
            elif approval.action == ModelApproval.ACTION_VERIFIED:
                if approval.value > 0:
                    bits.append("V+" + str(approval.value))
                elif approval.value < 0:
                    bits.append("V" + str(approval.value))
                else:
                    bits.append("V=0")
        return ",".join(bits)

    @staticmethod
    def format_event(event, bots, projects, usecolor):
        if event.user is None or event.change is None:
            return

        if event.is_user_in_list(bots):
            return
        if len(projects) > 0 and event.change.project not in projects:
            return

        change = event.change
        print (format_color("Change %s (%s)" % (change.url, change.id),
                            usecolor,
                            fg="red",
                            styles=["bold"]))
        print ("")
        print ("  Project: %s" % change.project)
        print ("  Subject: %s" % change.subject)
        if type(event) == ModelEventChangeRestore:
            print ("   Action: %s" % format_color("change restored", styles=["bold"]))
        elif type(event) == ModelEventChangeAbandon:
            print ("   Action: %s" % format_color("change abandoned", styles=["bold"]))
        elif type(event) == ModelEventChangeMerge:
            print ("   Action: %s" % format_color("change merged", styles=["bold"]))
        elif type(event) == ModelEventCommentAdd:
            print ("   Action: %s" % format_color("comment added", styles=["bold"]))
            if len(event.approvals) > 0:
                print ("    Votes: %s" %
                       format_color(CommandWatch.format_approvals(event.approvals),
                                    usecolor,
                                    fg="blue",
                                    styles=["bold"]))

        elif type(event) == ModelEventPatchCreate:
            print ("   Action: %s" % format_color("change restored", styles=["bold"]))

        if type(event) == ModelEventCommentAdd:
            print ("")
            CommandWatch.format_comment(event.comment, event.user, usecolor)
        print ("")
        print ("")


    def run(self, config, client, options):
        watch = OperationWatch(client)

        if options.all:
            bots = []
        else:
            bots = config.get_organization_bots()

        projects = self.get_projects(config, options)

        def cb(event):
            self.format_event(event,
                              bots,
                              projects,
                              options.color)

        return watch.run(cb)


class CommandReport(Command):

    def __init__(self, name, help):
        super(CommandReport, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandReport, self).add_options(parser, config)

        self.add_option(parser, config,
                        "-m", "--mode", default=ReportOutput.DISPLAY_MODE_TEXT,
                        help="Display output in 'text', 'json', 'xml', 'csv'")
        self.add_option(parser, config,
                        "--color", default=False, action="store_true",
                        help="Use terminal color highlighting")

    def get_report(self, config, client, options):
        raise NotImplementedError("subclass must override get_query")

    def run(self, config, client, options):
        report = self.get_report(config, client, options)

        report.display(options.mode)


class CommandReportTable(CommandReport):

    def __init__(self, name, help):
        super(CommandReportTable, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandReportTable, self).add_options(parser, config)

        self.add_option(parser, config,
                        "-l", "--limit", default=None,
                        help="Limit to N results")

        self.sort_option = self.add_option(parser, config,
                                           "--sort", default=None,
                                           help="Set the sort field")
        self.add_option(parser, config,
                        "--field", default=[],
                        action="append",
                        help="Display the named field")

    def run(self, config, client, options):
        report = self.get_report(config, client, options)

        if options.limit is not None:
            report.set_data_limit(int(options.limit))

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

        report.display(options.mode)


class CommandPatchReviewStats(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="patchreviewstats", help="Statistics on patch review approvals"):
        super(CommandPatchReviewStats, self).__init__(name, help)
        self.teams = {}
        self.set_long_cache(True)

    def add_options(self, parser, config):
        super(CommandPatchReviewStats, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--days", default=30,
                        help="Set number of days history to consult")

    def get_report(self, config, client, options):
        if options.all_groups:
            groups = config.get_organization_groups()
        else:
            groups = options.group

        teams = {}
        for team in config.get_organization_teams():
            teams[team] = []
            for group in groups:
                users = config.get_group_team_members(group, team)
                teams[team].extend(users)

        return ReportPatchReviewStats(client,
                                      self.get_projects(config, options, True),
                                      int(options.days),
                                      teams,
                                      usecolor=options.color)

    def run(self, config, client, options):
        return super(CommandPatchReviewStats, self).run(config, client, options)


class CommandPatchReviewRate(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="patchreviewrate", help="Daily review rate averaged per week"):
        super(CommandPatchReviewRate, self).__init__(name, help)
        self.teams = {}
        self.set_long_cache(True)

    def get_report(self, config, client, options):
        if options.all_groups:
            groups = config.get_organization_groups()
        else:
            groups = options.group

        teams = {}
        for team in config.get_organization_teams():
            teams[team] = []
            for group in groups:
                users = config.get_group_team_members(group, team)
                teams[team].extend(users)

        return ReportPatchReviewRate(client,
                                     self.get_projects(config, options, True),
                                     teams,
                                     usecolor=options.color)

    def run(self, config, client, options):
        return super(CommandPatchReviewRate, self).run(config, client, options)


class CommandOpenReviewStats(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="openreviewstats", help="Statistics on open patch reviews"):
        super(CommandOpenReviewStats, self).__init__(name, help)
        self.teams = {}
        self.set_long_cache(True)

    def add_options(self, parser, config):
        super(CommandOpenReviewStats, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--branch", default="master",
                        help="Set branch name to query")
        self.add_option(parser, config,
                        "--days", default=7,
                        help="Show count waiting more than N days")
        self.add_option(parser, config,
                        "--topic", default="",
                        help="Set topic name to query")

    def get_report(self, config, client, options):
        return ReportOpenReviewStats(client,
                                     self.get_projects(config, options, True),
                                     options.branch,
                                     options.topic,
                                     int(options.days),
                                     usecolor=options.color)

    def run(self, config, client, options):
        if options.limit is None:
            options.limit = 5

        return super(CommandOpenReviewStats, self).run(config, client, options)


class CommandChanges(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="changes", help="Query project changes"):
        super(CommandChanges, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandChanges, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--status", action="append", default=[],
                        help="Filter based on status")
        self.add_option(parser, config,
                        "--reviewer", action="append", default=[],
                        help="Filter based on reviewer")
        self.add_option(parser, config,
                        "--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "--topic", action="append", default=[],
                        help="Filter based on topic")
        self.add_option(parser, config,
                        "--message", action="append", default=[],
                        help="Filter based on message")
        self.add_option(parser, config,
                        "--owner", action="append", default=[],
                        help="Filter based on owner")
        self.add_option(parser, config,
                        "--approval", action="append", default=[],
                        help="Filter based on approval")
        self.add_option(parser, config,
                        "--rawquery", default=None,
                        help="Raw query string to pass through to gerrit")
        self.add_option(parser, config,
                        "file", default=[], nargs="*",
                        help="File name matches")
        self.sort_option.choices = [c.key for c in ReportChanges.COLUMNS]

    def get_report(self, config, client, options):
        return ReportChanges(client,
                             self.get_projects(config, options),
                             status=options.status,
                             reviewers=options.reviewer,
                             branches=options.branch,
                             topics=options.topic,
                             messages=options.message,
                             owners=options.owner,
                             approvals=options.approval,
                             rawquery=options.rawquery,
                             files=options.file,
                             usecolor=options.color)

class CommandToDoMine(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="todo-mine", help="List of changes I've looked at before"):
        super(CommandToDoMine, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandToDoMine, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "--topic", action="append", default=[],
                        help="Filter based on topic")
        self.add_option(parser, config,
                        "file", default=[], nargs="*",
                        help="File name matches")

    def get_report(self, config, client, options):
        username = config.get_server_username()
        if username is None:
            username = getpass.getuser()

        return ReportToDoListMine(client,
                                  username=username,
                                  projects=self.get_projects(config, options),
                                  branches=options.branch,
                                  files=options.file,
                                  topics=options.topic,
                                  usecolor=options.color)


class CommandToDoOthers(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="todo-others", help="List of changes I've not looked at before"):
        super(CommandToDoOthers, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandToDoOthers, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "--topic", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "file", default=[], nargs="*",
                        help="File name matches")

    def get_report(self, config, client, options):
        username = config.get_server_username()
        if username is None:
            username = getpass.getuser()

        return ReportToDoListOthers(client,
                                    username=username,
                                    projects=self.get_projects(config, options),
                                    branches=options.branch,
                                    files=options.file,
                                    topics=options.topic,
                                    usecolor=options.color)


class CommandToDoAnyones(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="todo-anyones", help="List of changes anyone has looked at"):
        super(CommandToDoAnyones, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandToDoAnyones, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "--topic", action="append", default=[],
                        help="Filter based on topic")
        self.add_option(parser, config,
                        "file", default=[], nargs="*",
                        help="File name matches")

    def get_report(self, config, client, options):
        username = config.get_server_username()
        if username is None:
            username = getpass.getuser()

        return ReportToDoListAnyones(client,
                                     username=username,
                                     bots=config.get_organization_bots(),
                                     projects=self.get_projects(config, options),
                                     branches=options.branch,
                                     files=options.file,
                                     topics=options.topic,
                                     usecolor=options.color)


class CommandToDoNoones(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="todo-noones", help="List of changes no one has looked at yet"):
        super(CommandToDoNoones, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandToDoNoones, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "--topic", action="append", default=[],
                        help="Filter based on topic")
        self.add_option(parser, config,
                        "file", default=[], nargs="*",
                        help="File name matches")

    def get_report(self, config, client, options):
        return ReportToDoListNoones(client,
                                    bots=config.get_organization_bots(),
                                    projects=self.get_projects(config, options),
                                    branches=options.branch,
                                    files=options.file,
                                    topics=options.topic,
                                    usecolor=options.color)


class CommandToDoApprovable(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="todo-approvable", help="List of changes that I can approve"):
        super(CommandToDoApprovable, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandToDoApprovable, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "--topic", action="append", default=[],
                        help="Filter based on topic")
        self.add_option(parser, config,
                        "--strict", action="store_true", default=False,
                        help="Exclude changes with any negative code reviews")
        self.add_option(parser, config,
                        "file", default=[], nargs="*",
                        help="File name matches")

    def get_report(self, config, client, options):
        username = config.get_server_username()
        if username is None:
            username = getpass.getuser()

        return ReportToDoListApprovable(client,
                                        username=username,
                                        strict=options.strict,
                                        projects=self.get_projects(config, options),
                                        branches=options.branch,
                                        files=options.file,
                                        topics=options.topic,
                                        usecolor=options.color)


class CommandToDoExpirable(CommandProject, CommandCaching, CommandReportTable):

    def __init__(self, name="todo-expirable", help="List of stale changes that can be expired"):
        super(CommandToDoExpirable, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandToDoExpirable, self).add_options(parser, config)

        self.add_option(parser, config,
                        "--branch", action="append", default=[],
                        help="Filter based on branch")
        self.add_option(parser, config,
                        "--topic", action="append", default=[],
                        help="Filter based on topic")
        self.add_option(parser, config,
                        "--age", default="28",
                        help="Set age cutoff in days")
        self.add_option(parser, config,
                        "file", default=[], nargs="*",
                        help="File name matches")

    def get_report(self, config, client, options):
        return ReportToDoListExpirable(client,
                                       age=int(options.age),
                                       projects=self.get_projects(config, options),
                                       branches=options.branch,
                                       files=options.file,
                                       topics=options.topic,
                                       usecolor=options.color)


class CommandComments(CommandCaching):

    def __init__(self, name="comments", help="Display comments on a change"):
        super(CommandComments, self).__init__(name, help)

    def add_options(self, parser, config):
        super(CommandComments, self).add_options(parser, config)

        self.add_option(parser, config,
                        "change", default=None,
                        help="Filter based on status")

        self.add_option(parser, config,
                        "--color", default=False, action="store_true",
                        help="Use terminal color highlighting")

        self.add_option(parser, config,
                        "--all", default=False, action="store_true",
                        help="Don't filter list of comments to strip bots")

        self.add_option(parser, config,
                        "--current", default=False, action="store_true",
                        help="Only display comments against current patch")

        self.add_option(parser, config,
                        "--patch", default=0,
                        help="Only display comments against patch NN")


    @staticmethod
    def wrap_text(message, indent="", width=78):
        lines = textwrap.wrap(message, width)
        return "\n".join(map(lambda x: indent + x, lines))

    @staticmethod
    def format_comments(allcomments, bots, usecolor):
        comments = []
        for comment in allcomments:
            if not comment.is_reviewer_in_list(bots):
                comments.append(comment)

        if len(comments) == 0:
            print (format_color("  No  comments",
                                usecolor,
                                fg="grey"))
            print ("")
            print ("")
        else:
            for comment in comments:
                if comment.file is not None:
                    print ("  %s: (%s) %s:%d" %
                           (format_color(comment.reviewer.name,
                                         usecolor,
                                         styles=["bold"]),
                            comment.reviewer.username,
                            comment.file,
                            comment.line))
                else:
                    print ("  %s: (%s)" %
                           (format_color(comment.reviewer.name,
                                         usecolor,
                                         styles=["bold"]),
                            comment.reviewer.username))
                print ("")
                print (CommandComments.wrap_text(comment.message, "  "))
                print ("")
                print ("")

    @staticmethod
    def format_change(change, bots, usecolor, currentpatch, patchnum):
        print (format_color("Change %s (%s)" % (change.url, change.id),
                            usecolor,
                            fg="red",
                            styles=["bold"]))
        print ("")
        print ("  %s" % change.subject)
        print ("")
        print ("")

        patches = change.patches
        if currentpatch:
            patches = patches[-1:]
        elif patchnum:
            patches = patches[patchnum-1:patchnum]

        for patch in patches:
            print (format_color("Patch %d (%s)" % (patch.number, patch.revision),
                                usecolor,
                                fg="blue",
                                styles=["bold"]))
            print ("")
            comments = []
            comments.extend(patch.comments)

            prefix = "Patch Set %d:" % patch.number
            abandoned = 0
            for comment in change.comments:
                if comment.message.startswith(prefix):
                    comments.append(comment)
                    if comment.message.startswith(prefix + ": Abandoned"):
                        abandoned = patch.number
                elif comment.message.startswith("Restored") and abandoned == patch.number:
                    comments.append(comment)

            CommandComments.format_comments(comments, bots, usecolor)


    def run(self, config, client, options):
        change = options.change

        query = OperationQuery(client,
                               {
                                   "change": [ change ],
                               },
                               patches=OperationQuery.PATCHES_ALL,
                               approvals=True,
                               files=True,
                               comments=True)

        if options.all:
            bots = []
        else:
            bots = config.get_organization_bots()

        def mycb(change):
            self.format_change(change, bots, options.color, options.current, int(options.patch))

        query.run(mycb, limit=1)


class CommandTool(object):

    def __init__(self):
        self.commands = {}

    def add_options(self, parser):
        parser.add_argument("-c", "--config", default=os.path.expanduser("~/.gerrymander"),
                            help=("Override config file (default %s)" %
                                  os.path.expanduser("~/.gerrymander")))
        parser.add_argument("-d", "--debug",
                            help="Display debugging information",
                            action="store_true")
        parser.add_argument("-q", "--quiet",
                            help="Supress display of warnings",
                            action="store_true")

    def add_command(self, subparser, config, cmdclass, name=None, help=None):
        cmd = cmdclass()
        if name is not None:
            cmd.name = name
        if help is not None:
            cmd.help = help

        parser = subparser.add_parser(cmd.name, help=cmd.help)
        cmd.add_options(parser, config)
        parser.set_defaults(func=cmd.execute)
        self.commands[cmd.name] = cmd

    def add_default_commands(self, subparser, config):
        self.add_command(subparser, config, CommandWatch)
        self.add_command(subparser, config, CommandToDoNoones)
        self.add_command(subparser, config, CommandToDoAnyones)
        self.add_command(subparser, config, CommandToDoMine)
        self.add_command(subparser, config, CommandToDoOthers)
        self.add_command(subparser, config, CommandToDoApprovable)
        self.add_command(subparser, config, CommandToDoExpirable)
        self.add_command(subparser, config, CommandPatchReviewStats)
        self.add_command(subparser, config, CommandPatchReviewRate)
        self.add_command(subparser, config, CommandOpenReviewStats)
        self.add_command(subparser, config, CommandChanges)
        self.add_command(subparser, config, CommandComments)

    def add_config_commands(self, subparser, config):
        aliases = config.get_command_aliases()
        for alias in aliases:
            basecmd = config.get_command_alias_basecmd(alias)
            help = config.get_command_alias_help(alias)

            if basecmd not in self.commands:
                raise Exception("Unknown base command '%s'" % basecmd)

            klass = type(self.commands[basecmd])
            self.add_command(subparser, config, klass, alias, help)

    def get_config(self, options):
        return CommandConfig(options.config)

    def execute(self, argv):
        miniparser = argparse.ArgumentParser(add_help=False)
        miniparser.add_argument("-c", "--config", default=os.path.expanduser("~/.gerrymander"),
                                help=("Override config file (default %s)" %
                                      os.path.expanduser("~/.gerrymander")))
        options, remaining = miniparser.parse_known_args(argv)

        config = CommandConfig(options.config)


        parser = argparse.ArgumentParser(description="Gerrymander client")
        self.add_options(parser)
        subparser = parser.add_subparsers()
        subparser.required = True
        subparser.dest = "command"
        self.add_default_commands(subparser, config)
        self.add_config_commands(subparser, config)

        options = parser.parse_args(argv)


        level = logging.WARNING
        if options.debug:
            level = logging.DEBUG
        elif options.quiet:
            level = logging.ERROR

        logging.basicConfig(level=level,
                            format='%(asctime)s %(levelname)s: %(message)s',
                            stream=sys.stderr)

        options.func(config, options)
