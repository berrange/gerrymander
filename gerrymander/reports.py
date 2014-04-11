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

from gerrymander.operations import OperationQuery
from gerrymander.model import ModelApproval

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

    def get_value(self, row):
        val = self.mapfunc(self.key, row)
        if self.truncate and len(val) > self.truncate:
            val = val[0:self.truncate] + "..."
        elif self.format is not None:
            val = self.format % val
        return val

    def get_sort_value(self, row):
        if self.sortfunc:
            return self.sortfunc(self.key, row)
        else:
            return self.mapfunc(self.key, row)


class Report(object):

    def __init__(self, client, columns, sort=None, reverse=False):
        self.client = client
        self.columns = columns
        self.sort = sort
        self.reverse = reverse

    def get_columns(self):
        return self.headers

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
            items.sort(key = lambda item: sortcol.get_sort_value(item), reverse=self.reverse)

        if limit is not None:
            items = items[0:limit]

        for item in items:
            row = []
            for col in self.columns:
                if col.visible:
                    row.append(col.get_value(item))
            table.add_row(row)

        return table


class ReportPatchReviewStats(Report):

    def review_mapfunc(col, row):
        return row[1]['total']

    def ratio_mapfunc(col, row):
        plus = float(row[1]['votes']['flag-p2'] + row[1]['votes']['flag-p1'])
        minus = float(row[1]['votes']['flag-m2'] + row[1]['votes']['flag-m1'])
        ratio = (plus / (plus + minus)) * 100
        return ratio

    def vote_mapfunc(col, row):
        return row[1]['votes'][col]

    COLUMNS = [
        ReportColumn("user", "User",  lambda col, row: row[0], align=ReportColumn.ALIGN_LEFT),
        ReportColumn("reviews", "Reviews", review_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-m2", "-2", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-m1", "-1", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-p1", "+1", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("flag-p2", "+2", vote_mapfunc, align=ReportColumn.ALIGN_RIGHT),
        ReportColumn("ratio", "+/-", ratio_mapfunc, format="%0.0lf%%", align=ReportColumn.ALIGN_RIGHT),
    ]

    def __init__(self, client, projects):
        Report.__init__(self, client, ReportPatchReviewStats.COLUMNS,
                        sort="reviews", reverse=True)
        self.projects = projects

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

            query.run(querycb, limit=20000)

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

