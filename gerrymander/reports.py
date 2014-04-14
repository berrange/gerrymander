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


import prettytable
import logging

from gerrymander.operations import OperationQuery
from gerrymander.model import ModelApproval
from gerrymander.format import format_date

LOG = logging.getLogger(__name__)

class ReportColumn(object):

    ALIGN_LEFT = "l"
    ALIGN_RIGHT = "r"
    ALIGN_CENTER = "c"

    def __init__(self, key, label, mapfunc, sortfunc=None, format=None, truncate=0, align=ALIGN_LEFT, visible=True):
        self.key = key
        self.label = label
        self.mapfunc = mapfunc
        self.sortfunc = sortfunc
        self.format = format
        self.truncate = truncate
        self.align = align
        self.visible = visible

    def get_value(self, report, row):
        val = self.mapfunc(report, self.key, row)
        if self.truncate and len(val) > self.truncate:
            val = val[0:self.truncate] + "..."
        elif self.format is not None:
            val = self.format % val
        return val

    def get_sort_value(self, report, row):
        if self.sortfunc:
            return self.sortfunc(report, self.key, row)
        else:
            return self.mapfunc(report, self.key, row)


class Report(object):

    def __init__(self, client, columns, sort=None, reverse=False):
        self.client = client
        self.columns = columns
        self.set_sort_column(sort, reverse)

    def get_columns(self):
        return self.columns

    def get_column(self, key):
        for col in self.columns:
            if col.key == key:
                return col
        return None

    def has_column(self, key):
        col = self.get_column(key)
        if col is None:
            return False
        return True

    def set_sort_column(self, key, reverse=False):
        got = False
        for col in self.columns:
            if col.key == key:
                got = True
        if not got:
            raise Exception("Unknown sort column %s" % key)
        self.sort = key
        self.reverse = reverse

    def generate(self):
        raise NotImplementedError("Subclass must override generate method")

    def get_table(self, limit=None):
        labels = []
        for col in self.columns:
            if col.visible:
                labels.append(col.label)
        table = prettytable.PrettyTable(labels)
        sortcol = None
        for col in self.columns:
            table.align[col.label] = col.align
            if col.key == self.sort:
                sortcol = col

        table.padding_width = 1

        items = self.generate()

        if sortcol is not None:
            items.sort(key = lambda item: sortcol.get_sort_value(self, item),
                       reverse=self.reverse)

        if limit is not None:
            items = items[0:limit]

        for item in items:
            row = []
            for col in self.columns:
                if col.visible:
                    row.append(col.get_value(self, item))
            table.add_row(row)

        return table


class ReportPatchReviewStats(Report):

    def user_mapfunc(rep, col, row):
        user = row[0]

        for team in rep.teams.keys():
            if user in rep.teams[team]:
                return user + " " + team

        return user

    def review_mapfunc(rep, col, row):
        return row[1]['total']

    def ratio_mapfunc(rep, col, row):
        plus = float(row[1]['votes']['flag-p2'] + row[1]['votes']['flag-p1'])
        minus = float(row[1]['votes']['flag-m2'] + row[1]['votes']['flag-m1'])
        ratio = (plus / (plus + minus)) * 100
        return ratio

    def vote_mapfunc(rep, col, row):
        return row[1]['votes'][col]

    COLUMNS = [
        ReportColumn("user", "User", user_mapfunc, align=ReportColumn.ALIGN_LEFT),
        ReportColumn("reviews", "Reviews", review_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-m2", "-2", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-m1", "-1", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-p1", "+1", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-p2", "+2", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("ratio", "+/-", ratio_mapfunc, format="%0.0lf%%", align=ReportColumn.ALIGN_RIGHT),
    ]

    def __init__(self, client, projects, teams={}):
        Report.__init__(self, client, ReportPatchReviewStats.COLUMNS,
                        sort="reviews", reverse=True)
        self.projects = projects
        self.teams = teams

    def generate(self):
        # We could query all projects at once, but if we do them
        # individually it means we get better hit rate against the
        # cache if the report is re-run for many different project
        # combinations
        reviews = []
        for project in self.projects:
            query = OperationQuery(self.client,
                                   {
                                       "project": [project],
                                   },
                                   patches=OperationQuery.PATCHES_ALL,
                                   approvals=True)


            def querycb(change):
                for patch in change.patches:
                    for approval in patch.approvals:
                        reviews.append(approval)

            query.run(querycb)

        reviewers = {}
        for review in reviews:
            if review.action != ModelApproval.ACTION_REVIEWED or review.user is None:
                continue

            reviewer = review.user.username

            if reviewer is not None and reviewer.lower() in ["jenkins", "smokestack"]:
                continue

            reviewers.setdefault(reviewer,
                                 {
                                     'votes': {'flag-m2': 0, 'flag-m1': 0, 'flag-p1': 0, 'flag-p2': 0},
                                     'total': 0,
                                 })
            reviewers[reviewer]['total'] = reviewers[reviewer]['total'] + 1
            votes = { "-2" : "flag-m2",
                      "-1" : "flag-m1",
                      "1" : "flag-p1",
                      "2" : "flag-p2" }
            cur = reviewers[reviewer]['votes'][votes[review.value]]
            reviewers[reviewer]['votes'][votes[review.value]] = cur + 1

        reviewers = [(k, v) for k, v in reviewers.items()]
        return reviewers


class ReportBaseChange(Report):
    def approvals_mapfunc(rep, col, row):
        patch = row.get_current_patch()
        if patch is None:
            LOG.error("No patch")
            return ""
        vals = {}
        for approval in patch.approvals:
            got_type = approval.action[0:1].lower()
            if got_type not in vals:
                vals[got_type] = []
            vals[got_type].append(approval.value)
        keys = list(vals.keys())
        keys.sort(reverse=True)
        return " ".join(map(lambda val: "%s=%s" % (val,
                                                   ",".join(vals[val])), keys))

    def user_mapfunc(rep, col, row):
        if not row.owner or not row.owner.username:
            return "<unknown>"
        return row.owner.username

    def date_mapfunc(rep, col, row):
        if col == "lastUpdated":
            return format_date(row.lastUpdated)
        else:
            return format_date(row.createdOn)

    def date_sortfunc(rep, col, row):
        if col == "lastUpdated":
            return row.lastUpdated
        else:
            return row.createdOn

    COLUMNS = [
        ReportColumn("status", "Status", lambda rep, col, row: row.status),
        ReportColumn("topic", "Topic", lambda rep, col, row: row.topic, visible=False),
        ReportColumn("url", "URL", lambda rep, col, row: row.url),
        ReportColumn("owner", "Owner", user_mapfunc),
        ReportColumn("project", "Project", lambda rep, col, row: row.project, visible=False),
        ReportColumn("branch", "Branch", lambda rep, col, row: row.branch, visible=False),
        ReportColumn("subject", "Subject", lambda rep, col, row: row.subject, truncate=30),
        ReportColumn("createdOn", "Created", date_mapfunc, date_sortfunc),
        ReportColumn("lastUpdated", "Updated", date_mapfunc, date_sortfunc),
        ReportColumn("approvals", "Approvals", approvals_mapfunc),
    ]

    def __init__(self, client):
        Report.__init__(self, client, ReportBaseChange.COLUMNS,
                        sort="createdOn", reverse=False)

class ReportChanges(ReportBaseChange):

    def __init__(self, client, projects=[], owners=[],
                 status=[], messages=[], branches=[], reviewers=[],
                 approvals=[], files=[]):
        ReportBaseChange.__init__(self, client)
        self.projects = projects
        self.owners = owners
        self.status = status
        self.messages = messages
        self.branches = branches
        self.reviewers = reviewers
        self.approvals = approvals
        self.files = files

    def generate(self):
        needFiles = False
        if len(self.files) > 0:
            needFiles = True

        query = OperationQuery(self.client,
                               {
                                   "project": self.projects,
                                   "owner": self.owners,
                                   "message": self.messages,
                                   "branch": self.branches,
                                   "status": self.status,
                                   "reviewer": self.reviewers,
                               },
                               patches=OperationQuery.PATCHES_CURRENT,
                               approvals=True,
                               files=needFiles)

        changes = []

        def match_files(change):
            if len(self.files) == 0:
                return True
            for filere in self.files:
                for patch in change.patches:
                    for file in patch.files:
                        if re.search(filere, file):
                            return True
            return False

        def querycb(change):
            if match_files(change):
                changes.append(change)

        query.run(querycb)

        return changes


class ReportToDoList(ReportBaseChange):

    def __init__(self, client, projects=[], reviewers=[]):
        ReportBaseChange.__init__(self, client)

        self.projects = projects
        self.reviewers = reviewers

    def filter(self, change):
        return True

    def generate(self):
        query = OperationQuery(self.client,
                               {
                                   "project": self.projects,
                                   "status": [ OperationQuery.STATUS_OPEN ],
                                   "reviewer": self.reviewers,
                               },
                               patches=OperationQuery.PATCHES_ALL,
                               approvals=True)

        changes = []

        def querycb(change):
            if self.filter(change):
                changes.append(change)

        query.run(querycb)

        return changes




class ReportToDoListMine(ReportToDoList):

    def __init__(self, client, username, projects=[]):
        '''
        Report to provide a list of changes 'username' has
        reviewed an older version of the patch, and needs
        to provide feedback on latest version
        '''
        ReportToDoList.__init__(self, client,
                                projects,
                                reviewers=[ username ])
        self.username = username

    def filter(self, change):
        if not change.has_current_reviewers([self.username]):
            return True
        return False


class ReportToDoListOthers(ReportToDoList):
    def __init__(self, client, username, bots=[], projects=[]):
        '''
        Report to provide a list of changes where 'username' has
        never reviewed, but at least one other non-bot user has
        provided review
        '''
        ReportToDoList.__init__(self, client,
                                projects,
                                reviewers=[ "!", username ])
        self.bots = bots

    def filter(self, change):
        # allchanges contains changes where 'username' has
        # not reviewed any version of the patch. We want to
        # filter out changes which only have bots, or have
        # no reviewers at all.
        if change.has_any_other_reviewers(self.bots):
            return True


class ReportToDoListAnyones(ReportToDoList):

    def __init__(self, client, bots=[], projects=[]):
        '''
        Report to provide a list of changes where at least
        one other non-bot user has provided review
        '''
        ReportToDoList.__init__(self, client,
                                projects)
        self.bots = bots

    def filter(self, change):
        if change.has_any_other_reviewers(self.bots):
            return True


class ReportToDoListNoones(ReportToDoList):

    def __init__(self, client, bots=[], projects=[]):
        '''
        Report to provide a list of changes that no one
        has ever reviewed
        '''
        ReportToDoList.__init__(self, client,
                                projects)
        self.bots = bots

    def filter(self, change):
        if not change.has_any_other_reviewers(self.bots):
            return True
