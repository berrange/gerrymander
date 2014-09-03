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


import collections
import prettytable
import logging
import time
import re
import json
import sys
import xml.dom.minidom

from gerrymander.operations import OperationQuery
from gerrymander.model import ModelApproval
from gerrymander.format import format_date
from gerrymander.format import format_delta
from gerrymander.format import format_title
from gerrymander.format import format_color

LOG = logging.getLogger(__name__)

class ReportOutputColumn(object):

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
        if self.format is not None:
            val = self.format % val
        elif val is None:
            val = ""

        if type(val) != str:
            val = val.encode('utf-8')

        if self.truncate and len(val) > self.truncate:
            val = val[0:self.truncate] + "..."

        return val

    def get_sort_value(self, report, row):
        if self.sortfunc:
            return self.sortfunc(report, self.key, row)
        else:
            return self.mapfunc(report, self.key, row)

class ReportOutput(object):

    DISPLAY_MODE_TEXT = "text"
    DISPLAY_MODE_CSV = "csv"
    DISPLAY_MODE_XML = "xml"
    DISPLAY_MODE_JSON = "json"

    def __init__(self, usecolor=False):
        super(ReportOutput, self).__init__()
        self.usecolor = usecolor

    def display(self, mode, stream=sys.stdout):
        if mode == ReportOutput.DISPLAY_MODE_TEXT:
            stream.write(self.to_text())
        elif mode == ReportOutput.DISPLAY_MODE_CSV:
            stream.write(self.to_csv())
        elif mode == ReportOutput.DISPLAY_MODE_XML:
            impl = xml.dom.minidom.getDOMImplementation()
            doc = impl.createDocument(None, "report", None)
            self.to_xml(doc, doc.documentElement)
            stream.write(doc.toprettyxml())
        elif mode == ReportOutput.DISPLAY_MODE_JSON:
            doc = []
            self.to_json(doc)
            stream.write(json.dumps(doc, indent=2) + "\n")
        else:
            raise Exception("Unknown display mode '%s'" % mode)

    def to_text(self):
        raise NotImplementedError("Subclass should implement the 'to_text' method")

    def to_csv(self):
        raise NotImplementedError("Subclass should implement the 'to_csv' method")

    def to_xml(self, root):
        raise NotImplementedError("Subclass should implement the 'to_xml' method")

    def to_json(self, root):
        raise NotImplementedError("Subclass should implement the 'to_json' method")


class ReportOutputCompound(ReportOutput):

    def __init__(self):
        self.report = []

    def add_report(self, report):
        self.report.append(report)

    def to_text(self):
        blocks = []
        for report in self.report:
            blocks.append(report.to_text())
        return "\n".join(blocks)

    def to_json(self, root):
        for report in self.report:
            report.to_json(root)

    def to_xml(self, doc, root):
        for report in self.report:
            report.to_xml(doc, root)


class ReportOutputList(ReportOutput):
    def __init__(self, columns, title=None, usecolor=False):
        super(ReportOutputList, self).__init__(usecolor)
        self.columns = columns
        self.row = {}
        self.title = title

    def set_row(self, row):
        self.row = row

    def to_xml(self, doc, root):
        lst = doc.createElement("list")
        root.appendChild(lst)
        if self.title is not None:
            title = doc.createElement("title")
            title.appendChild(doc.createTextNode(self.title))
            lst.appendChild(title)
        headers = doc.createElement("headers")
        content = doc.createElement("content")
        lst.appendChild(headers)
        lst.appendChild(content)

        for col in self.columns:
            if col.visible:
                xmlcol = doc.createElement(col.key)
                xmlcol.appendChild(doc.createTextNode(col.label))
                headers.appendChild(xmlcol)

        for col in self.columns:
            if col.visible:
                xmlfield = doc.createElement(col.key)
                xmlfield.appendChild(doc.createTextNode(col.get_value(self, self.row)))
                content.appendChild(xmlfield)

    def to_json(self, root):
        headers = {}
        for col in self.columns:
            if col.visible:
                headers[col.key] = col.label

        content = {}
        for col in self.columns:
            if col.visible:
                content[col.key] = col.get_value(self, self.row)

        node = {
            "list": {
                "headers": headers,
                "content": content
            }
        }
        if self.title is not None:
            node["list"]["title"] = self.title
        root.append(node)


    def to_text(self):
        labels = []
        width = 1
        for col in self.columns:
            if col.visible:
                if len(col.label) > width:
                    width = len(col.label)
                labels.append(col.label)

        fmt = "  %" + str(width) + "s: %s"
        lines = []
        for col in self.columns:
            if col.visible:
                line = fmt % (col.label, col.get_value(self, self.row))
            lines.append(line)

        prolog = ""
        if self.title is not None:
            prolog = format_title(self.title) + "\n"
        return prolog + "\n".join(lines) + "\n"


class ReportOutputTable(ReportOutput):
    def __init__(self, columns, sortcol, reverse, limit, title=None, usecolor=False):
        super(ReportOutputTable, self).__init__(usecolor)
        self.columns = list(columns)
        self.rows = []
        self.sortcol = sortcol
        self.reverse = reverse
        self.limit = limit
        self.title = title

    def add_column(self, col):
        self.columns.append(col)

    def add_row(self, row):
        self.rows.append(row)

    def sort_rows(self):
        sortcol = None
        for col in self.columns:
            if col.key == self.sortcol:
                sortcol = col

        if sortcol is not None:
            self.rows.sort(key = lambda item: sortcol.get_sort_value(self, item),
                           reverse=self.reverse)

    def to_xml(self, doc, root):
        self.sort_rows()

        table = doc.createElement("table")
        root.appendChild(table)
        if self.title is not None:
            title = doc.createElement("title")
            title.appendChild(doc.createTextNode(self.title))
            table.appendChild(title)
        headers = doc.createElement("headers")
        content = doc.createElement("content")
        table.appendChild(headers)
        table.appendChild(content)

        for col in self.columns:
            if col.visible:
                xmlcol = doc.createElement(col.key)
                xmlcol.appendChild(doc.createTextNode(col.label))
                headers.appendChild(xmlcol)

        rows = self.rows
        if self.limit is not None:
            rows = rows[0:self.limit]
        for row in rows:
            xmlrow = doc.createElement("row")
            for col in self.columns:
                if col.visible:
                    xmlfield = doc.createElement(col.key)
                    xmlfield.appendChild(doc.createTextNode(col.get_value(self, row)))
                    xmlrow.appendChild(xmlfield)
            content.appendChild(xmlrow)

        return doc

    def to_json(self, root):
        self.sort_rows()

        headers = {}
        for col in self.columns:
            if col.visible:
                headers[col.key] = col.label

        content = []
        rows = self.rows
        if self.limit is not None:
            rows = rows[0:self.limit]
        for row in rows:
            data = {}
            for col in self.columns:
                if col.visible:
                    data[col.key] = col.get_value(self, row)
            content.append(data)

        node = {
            "table": {
                "headers": headers,
                "content": content
            }
        }
        if self.title is not None:
            node["table"]["title"] = self.title
        root.append(node)

    def to_text(self):
        self.sort_rows()

        labels = []
        for col in self.columns:
            if col.visible:
                labels.append(col.label)
        table = prettytable.PrettyTable(labels)
        for col in self.columns:
            table.align[col.label] = col.align

        table.padding_width = 1

        rows = self.rows
        if self.limit is not None:
            rows = rows[0:self.limit]
        for row in rows:
            data = []
            for col in self.columns:
                if col.visible:
                    data.append(col.get_value(self, row))
            table.add_row(data)

        prolog = ""
        if self.title is not None:
            prolog = format_title(self.title) + "\n"
        return prolog + str(table) + "\n"

    def to_csv(self):
        self.sort_rows()

        labels = []
        for col in self.columns:
            if col.visible:
                labels.append(col.label)

        lines = []

        if self.title is not None:
            lines.append(self.title)

        lines.append(",".join(labels))

        rows = self.rows
        if self.limit is not None:
            rows = rows[0:self.limit]
        for row in rows:
            data = []
            for col in self.columns:
                if col.visible:
                    data.append(col.get_value(self, row))
            lines.append(",".join(data))

        return "\n".join(lines)


class Report(object):

    def __init__(self, client):
        self.client = client

    def generate(self):
        raise NotImplementedError("Subclass must override generate method")

    def display(self, mode):
        output = self.generate()
        output.display(mode)


class ReportTable(Report):

    def __init__(self, client, columns, sort=None, reverse=False):
        super(ReportTable, self).__init__(client)
        self.columns = columns
        self.limit = None
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

    def set_data_limit(self, limit):
        self.limit = limit

    def new_table(self, title=None):
        return ReportOutputTable(self.columns, self.sort,
                                 self.reverse, self.limit,
                                 title, self.usecolor)


class ReportPatchReviewStats(ReportTable):

    def user_mapfunc(rep, col, row):
        return row[0]

    def team_mapfunc(rep, col, row):
        return row[2]

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
        ReportOutputColumn("user", "User", user_mapfunc, align=ReportOutputColumn.ALIGN_LEFT),
        ReportOutputColumn("team", "Team", team_mapfunc, align=ReportOutputColumn.ALIGN_LEFT),
        ReportOutputColumn("reviews", "Reviews", review_mapfunc, align=ReportOutputColumn.ALIGN_RIGHT),
        ReportOutputColumn("flag-m2", "-2", vote_mapfunc, align=ReportOutputColumn.ALIGN_RIGHT),
        ReportOutputColumn("flag-m1", "-1", vote_mapfunc, align=ReportOutputColumn.ALIGN_RIGHT),
        ReportOutputColumn("flag-p1", "+1", vote_mapfunc, align=ReportOutputColumn.ALIGN_RIGHT),
        ReportOutputColumn("flag-p2", "+2", vote_mapfunc, align=ReportOutputColumn.ALIGN_RIGHT),
        ReportOutputColumn("ratio", "+/-", ratio_mapfunc, format="%0.0lf%%", align=ReportOutputColumn.ALIGN_RIGHT),
    ]

    def __init__(self, client, projects, maxagedays=30, teams={}, usecolor=False):
        super(ReportPatchReviewStats, self).__init__(client,
                                                     ReportPatchReviewStats.COLUMNS,
                                                     sort="reviews", reverse=True)
        self.projects = projects
        self.teams = teams
        self.maxagedays = maxagedays
        self.usecolor = usecolor

    def generate(self):
        # We could query all projects at once, but if we do them
        # individually it means we get better hit rate against the
        # cache if the report is re-run for many different project
        # combinations
        reviews = []
        cutoff = time.time() - (self.maxagedays * 24 * 60 * 60)
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
                        if approval.is_newer_than(cutoff):
                            reviews.append(approval)

            query.run(querycb)

        reviewers = {}
        for review in reviews:
            if review.action != ModelApproval.ACTION_REVIEWED or review.user is None:
                continue

            reviewer = review.user.username
            if reviewer is None:
                reviewer = review.user.name
                if reviewer is None:
                    continue

            if reviewer.lower() in ["jenkins", "smokestack"]:
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
            cur = reviewers[reviewer]['votes'][votes[str(review.value)]]
            reviewers[reviewer]['votes'][votes[str(review.value)]] = cur + 1

        compound = ReportOutputCompound()
        table = self.new_table("Review statistics")
        compound.add_report(table)

        for user, votes in reviewers.items():
            userteam = ""
            for team in self.teams.keys():
                if user in self.teams[team]:
                    userteam = team

            table.add_row([user, votes, userteam])

        summary = ReportOutputList([
            ReportOutputColumn("nreviews", "Total reviews", format="%d",
                               mapfunc=lambda rep, col, row: row[0]),
            ReportOutputColumn("nreviewers", "Total rviewers", format="%d",
                               mapfunc=lambda rep, col, row: row[1])
        ], title="Review summary")
        summary.set_row([len(reviews), len(reviewers.keys())])
        compound.add_report(summary)

        return compound


class ReportPatchReviewRate(ReportTable):

    def user_mapfunc(rep, col, row):
        return row[0]

    def team_mapfunc(rep, col, row):
        return row[1]

    def week_mapfunc(rep, col, row):
        if col not in row[2]:
            return 0.0

        return (row[2][col] / 7.0)

    def total_mapfunc(rep, col, row):
        if col not in row[2]:
            return 0.0

        return (row[2][col] / (52.0 * 7.0))

    COLUMNS = [
        ReportOutputColumn("user", "User", user_mapfunc, align=ReportOutputColumn.ALIGN_LEFT),
        ReportOutputColumn("team", "Team", team_mapfunc, align=ReportOutputColumn.ALIGN_LEFT),

        ReportOutputColumn("total", "Total", total_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week1", "1 week", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week2", "2 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week3", "3 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week4", "4 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week5", "5 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week6", "6 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week7", "7 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week8", "8 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week9", "9 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week10", "10 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week11", "11 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week12", "12 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week13", "13 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week14", "14 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week15", "15 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week16", "16 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week17", "17 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week18", "18 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week19", "19 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week20", "20 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week21", "21 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week22", "22 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week23", "23 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week24", "24 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week25", "25 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week26", "26 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week27", "27 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week28", "28 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week29", "29 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week30", "30 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week31", "31 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week32", "32 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week33", "33 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week34", "34 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week35", "35 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week36", "36 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week37", "37 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week38", "38 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week39", "39 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week40", "40 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week41", "41 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week42", "42 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week43", "43 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week44", "44 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week45", "45 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week46", "46 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week47", "47 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week48", "48 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),

        ReportOutputColumn("week49", "49 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week50", "50 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week51", "51 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
        ReportOutputColumn("week52", "52 weeks", week_mapfunc, align=ReportOutputColumn.ALIGN_LEFT, format="%0.2f"),
     ]

    def __init__(self, client, projects, teams={}, usecolor=False):
        super(ReportPatchReviewRate, self).__init__(client,
                                                    ReportPatchReviewRate.COLUMNS,
                                                    sort="total", reverse=True)
        self.projects = projects
        self.teams = teams
        self.usecolor = usecolor

    def generate(self):
        # We could query all projects at once, but if we do them
        # individually it means we get better hit rate against the
        # cache if the report is re-run for many different project
        # combinations
        reviewers = {}
        now = time.time()
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
                        if approval.action == ModelApproval.ACTION_VERIFIED:
                            continue

                        user = approval.user
                        if user is None or user.username is None:
                            continue
                        username = user.username

                        if username not in reviewers:
                            reviewers[username] = { "total": 0}

                        agesecs = approval.get_age(now)
                        ageweeks = int(agesecs / (60 * 60 * 24 * 7)) + 1
                        key = "week%d" % ageweeks

                        if key not in reviewers[username]:
                            reviewers[username][key] = 0

                        reviewers[username][key] = reviewers[username][key] + 1

                        if ageweeks <= 52:
                            reviewers[username]["total"] = reviewers[username]["total"] + 1

            query.run(querycb)

        table = self.new_table("Daily review rates per week")

        for reviewer in reviewers.keys():
            userteam = ""
            for team in self.teams.keys():
                if reviewer in self.teams[team]:
                    userteam = team

            table.add_row([reviewer, userteam, reviewers[reviewer]])

        return table


class ReportBaseChange(ReportTable):

    @staticmethod
    def get_approval_votes(patch):
        # Yes, the numbers are slightly odd order
        # A +2 or -2 more important than any -1 or +1
        # so we prefer them as the summary value
        levels = ["-2", "2", "-1", "1"]

        votes = {
            "c": { "total": collections.defaultdict(int),
                   "list": [],
                   "summary": "",
                   "details": "",
            },
            "v": { "total": collections.defaultdict(int),
                   "list": [],
                   "summary": "",
                   "details": "",
            },
            "w": { "total": collections.defaultdict(int),
                   "list": [],
                   "summary": "",
                   "details": "",
            },
        }

        for approval in patch.approvals:
            got_type = approval.action[0:1].lower()
            if got_type not in votes:
                continue
            vote = str(approval.value)
            votes[got_type]["total"][vote] = votes[got_type]["total"][vote] + 1
            votes[got_type]["list"].append(vote)

        for key in votes.keys():
            votes[key]["details"] = ",".join(votes[key]["list"])

            vals = []
            for level in levels:
                if level in votes[key]["total"]:
                    votes[key]["summary"] = level
                    break

        return votes

    def approvals_mapfunc(rep, col, row):
        patch = row.get_current_patch()
        if patch is None:
            LOG.error("No patch")
            return ""

        votes = ReportBaseChange.get_approval_votes(patch)
        keys = list(votes.keys())
        keys.sort(reverse=True)

        data = " ".join(map(lambda val: "%s=%s" % (val, votes[val]["details"]), keys))

        if rep.usecolor:
            if votes["w"]["total"]["1"] > 0: # Stuff pending merge
                return format_color(data, fg="blue", styles=["bold"])
            elif votes["w"]["total"]["-1"] > 0: # Work-in-progress
                return format_color(data, fg="magenta", styles=[])
            elif votes["c"]["total"]["-2"] > 0: # Hard-nack from core
                return format_color(data, fg="red", styles=["bold"])
            elif votes["c"]["total"]["-1"] > 0 or votes["v"]["total"]["-1"] > 0: # Nack from any or bots
                return format_color(data, fg="red", styles=[])
            elif votes["c"]["total"]["2"] > 0: # Approval from core
                return format_color(data, fg="green", styles=["bold"])
            elif votes["c"]["total"]["1"] > 0: # Approval from any
                return format_color(data, fg="green", styles=[])
            else:
                return data
        else:
            return data

    def votes_mapfunc(rep, col, row):
        patch = row.get_current_patch()
        if patch is None:
            LOG.error("No patch")
            return ""

        if col == "tests":
            coltype = "v"
        elif col == "reviews":
            coltype = "c"
        else:
            coltype = "w"

        votes = ReportBaseChange.get_approval_votes(patch)
        data = "%2s" % votes[coltype]["summary"]
        if rep.usecolor:
            if votes[coltype]["total"]["-2"] > 0: # Hard-nack from core
                return format_color(data, fg="red", styles=["bold"])
            elif votes[coltype]["total"]["2"] > 0: # Approval from core
                return format_color(data, fg="green", styles=["bold"])
            elif votes[coltype]["total"]["-1"] > 0: # Soft-nack from any
                return format_color(data, fg="red", styles=[])
            elif votes[coltype]["total"]["1"] > 0: # Approval from any
                return format_color(data, fg="green", styles=[])
            else:
                return data
        else:
            return data

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
        ReportOutputColumn("status", "Status", lambda rep, col, row: row.status),
        ReportOutputColumn("topic", "Topic", lambda rep, col, row: row.topic, visible=False),
        ReportOutputColumn("url", "URL", lambda rep, col, row: row.url),
        ReportOutputColumn("owner", "Owner", user_mapfunc),
        ReportOutputColumn("project", "Project", lambda rep, col, row: row.project, visible=False),
        ReportOutputColumn("branch", "Branch", lambda rep, col, row: row.branch, visible=False),
        ReportOutputColumn("subject", "Subject", lambda rep, col, row: row.subject, truncate=30),
        ReportOutputColumn("createdOn", "Created", date_mapfunc, date_sortfunc),
        ReportOutputColumn("lastUpdated", "Updated", date_mapfunc, date_sortfunc),
        ReportOutputColumn("approvals", "Approvals", approvals_mapfunc, visible=False),
        ReportOutputColumn("tests", "Tests", votes_mapfunc),
        ReportOutputColumn("reviews", "Reviews", votes_mapfunc),
        ReportOutputColumn("workflow", "Workflow", votes_mapfunc),
    ]

    def __init__(self, client, usecolor=False):
        super(ReportBaseChange, self).__init__(client, ReportBaseChange.COLUMNS,
                                               sort="createdOn", reverse=False)
        self.usecolor = usecolor


class ReportChanges(ReportBaseChange):

    def __init__(self, client, projects=[], owners=[],
                 status=[], messages=[], branches=[], topics=[], reviewers=[],
                 approvals=[], files=[], rawquery=None, usecolor=False):
        super(ReportChanges, self).__init__(client, usecolor)
        self.projects = projects
        self.owners = owners
        self.status = status
        self.messages = messages
        self.branches = branches
        self.topics = topics
        self.reviewers = reviewers
        self.approvals = approvals
        self.files = files
        self.rawquery = rawquery

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
                                   "topic": self.topics,
                                   "status": self.status,
                                   "reviewer": self.reviewers,
                               },
                               rawquery=self.rawquery,
                               patches=OperationQuery.PATCHES_CURRENT,
                               approvals=True,
                               files=needFiles)

        def match_files(change):
            if len(self.files) == 0:
                return True
            for filere in self.files:
                for patch in change.patches:
                    for file in patch.files:
                        if re.search(filere, file.path):
                            return True
            return False

        table = self.new_table("Changes")
        def querycb(change):
            if match_files(change):
                table.add_row(change)

        query.run(querycb)

        return table


class ReportToDoList(ReportBaseChange):

    def __init__(self, client, projects=[], branches=[],
                 files=[], topics=[], reviewers=[], usecolor=False):
        super(ReportToDoList, self).__init__(client, usecolor)

        self.projects = projects
        self.branches = branches
        self.reviewers = reviewers
        self.files = files
        self.topics = topics

    def filter(self, change):
        return True

    def generate(self):
        needFiles = False
        if len(self.files) > 0:
            needFiles = True

        query = OperationQuery(self.client,
                               {
                                   "project": self.projects,
                                   "status": [ OperationQuery.STATUS_OPEN ],
                                   "branch": self.branches,
                                   "topic": self.topics,
                                   "reviewer": self.reviewers,
                               },
                               patches=OperationQuery.PATCHES_ALL,
                               approvals=True,
                               files=needFiles)

        def match_files(change):
            if len(self.files) == 0:
                return True
            for filere in self.files:
                for patch in change.patches:
                    for file in patch.files:
                        if re.search(filere, file.path):
                            return True
            return False

        table = self.new_table("Changes To Do List")
        def querycb(change):
            if self.filter(change) and match_files(change):
                table.add_row(change)

        query.run(querycb)

        return table




class ReportToDoListMine(ReportToDoList):

    def __init__(self, client, username, projects=[],
                 branches=[], files=[], topics=[], usecolor=False):
        '''
        Report to provide a list of changes 'username' has
        reviewed an older version of the patch, and needs
        to provide feedback on latest version
        '''
        super(ReportToDoListMine, self).__init__(client,
                                                 projects,
                                                 reviewers=[ username ],
                                                 branches=branches,
                                                 files=files,
                                                 topics=topics,
                                                 usecolor=usecolor)
        self.username = username

    def filter(self, change):
        if (not change.has_current_reviewers([self.username]) and
            not change.has_owner([self.username])):
            return True
        return False


class ReportToDoListOthers(ReportToDoList):
    def __init__(self, client, username, bots=[], projects=[],
                 branches=[], files=[], topics=[], usecolor=False):
        '''
        Report to provide a list of changes where 'username' has
        never reviewed, but at least one other non-bot user has
        provided review
        '''
        super(ReportToDoListOthers, self).__init__(client,
                                                   projects,
                                                   reviewers=[ "!", username ],
                                                   branches=branches,
                                                   files=files,
                                                   topics=topics,
                                                   usecolor=usecolor)
        self.bots = bots

    def filter(self, change):
        # allchanges contains changes where 'username' has
        # not reviewed any version of the patch. We want to
        # filter out changes which only have bots, or have
        # no reviewers at all.
        if change.has_any_other_reviewers(self.bots):
            return True
        return False


class ReportToDoListAnyones(ReportToDoList):

    def __init__(self, client, username, bots=[], projects=[],
                 branches=[], files=[], topics=[], usecolor=False):
        '''
        Report to provide a list of changes where at least
        one other non-bot user has provided review
        '''
        super(ReportToDoListAnyones, self).__init__(client,
                                                    projects,
                                                    branches=branches,
                                                    files=files,
                                                    topics=topics,
                                                    usecolor=usecolor)
        self.bots = bots
        self.username = username

    def filter(self, change):
        if change.has_current_reviewers([self.username]):
            return False
        if change.has_any_other_reviewers(self.bots):
            return True
        return False


class ReportToDoListNoones(ReportToDoList):

    def __init__(self, client, bots=[], projects=[],
                 branches=[], files=[], topics=[], usecolor=False):
        '''
        Report to provide a list of changes that no one
        has ever reviewed
        '''
        super(ReportToDoListNoones, self).__init__(client,
                                                   projects,
                                                   branches=branches,
                                                   topics=topics,
                                                   usecolor=usecolor)
        self.bots = bots

    def filter(self, change):
        if not change.has_any_other_reviewers(self.bots):
            return True
        return False


class ReportToDoListApprovable(ReportToDoList):

    def __init__(self, client, username, strict, projects=[],
                 branches=[], files=[], topics=[], usecolor=False):
        '''
        Report to provide a list of changes that no one
        has ever reviewed
        '''
        super(ReportToDoListApprovable, self).__init__(client,
                                                       projects,
                                                       branches=branches,
                                                       files=files,
                                                       topics=topics,
                                                       usecolor=usecolor)
        self.username = username
        self.strict = strict

    def filter(self, change):
        if (change.has_current_approval(ModelApproval.ACTION_REVIEWED, 2) and
            not change.has_owner([self.username]) and
            not change.has_current_approval(ModelApproval.ACTION_WORKFLOW, -1) and
            not change.has_current_approval(ModelApproval.ACTION_WORKFLOW, 1) and
            not change.has_current_approval(ModelApproval.ACTION_REVIEWED, -2) and
            not change.has_current_reviewers([self.username])):

            if (self.strict and
                change.has_current_approval(ModelApproval.ACTION_REVIEWED, -1)):
                return False

            return True
        return False


class ReportToDoListExpirable(ReportToDoList):

    def __init__(self, client, age=28, projects=[],
                 branches=[], files=[], topics=[], usecolor=False):
        '''
        Report to provide a list of changes that are
        stale and can potentially be expired
        '''
        super(ReportToDoListExpirable, self).__init__(client,
                                                      projects,
                                                      branches=branches,
                                                      files=files,
                                                      topics=topics,
                                                      usecolor=usecolor)
        self.age = age

    def filter(self, change):
        if change.get_current_reviewer_nack_age() > (self.age * 24 * 60 * 60):
            return True
        return False


class ReportOpenReviewStats(ReportBaseChange):

    def __init__(self, client, projects, branch="master", topic="", days=7, usecolor=False):
        super(ReportOpenReviewStats, self).__init__(client, usecolor)
        self.projects = projects
        self.branch = branch
        self.topic = topic
        self.days = days

    @staticmethod
    def average_age(changes, ages):
        if len(changes) == 0:
            return 0
        total = 0
        for change in changes:
            total += ages[change]
        return format_delta(total / len(changes))

    @staticmethod
    def median_age(changes, ages):
        if len(changes) == 0:
            return 0
        total = 0
        wantages = []
        for change in changes:
            wantages.append(ages[change])
        wantages.sort()
        return format_delta(wantages[int(len(wantages)/2)])

    @staticmethod
    def older_than(changes, ages, cutoffdays):
        cutoff = cutoffdays * 24 * 60 * 60
        older = 0
        for change in changes:
            if ages[change] > cutoff:
                older = older + 1
        return older

    @staticmethod
    def get_longest_changes(ids, changes, ages, count):
        want = []
        for id in sorted(ids, key=lambda x: ages[x]):
            want.append(changes[id])
        return want

    def generate(self):
        # We could query all projects at once, but if we do them
        # individually it means we get better hit rate against the
        # cache if the report is re-run for many different project
        # combinations
        agecurrent = {}
        agefirst = {}
        agenonnacked = {}
        wait_reviewer = []
        wait_submitter = []
        changes = {}
        for project in self.projects:
            query = OperationQuery(self.client,
                                   {
                                       "project": [project],
                                       "status": [OperationQuery.STATUS_OPEN],
                                       "branch": [self.branch],
                                       "topic": [self.topic],
                                   },
                                   patches=OperationQuery.PATCHES_ALL,
                                   approvals=True)


            def querycb(change):
                if change.status != "NEW":
                    return

                now = time.time()
                current = change.get_current_patch()
                first = change.get_first_patch()
                nonnacked = change.get_reviewer_not_nacked_patch()

                changes[change.id] = change

                if current.is_nacked():
                    wait_submitter.append(change.id)
                else:
                    wait_reviewer.append(change.id)

                agecurrent[change.id] = current.get_age(now)
                agefirst[change.id] = first.get_age(now)
                if nonnacked:
                    agenonnacked[change.id] = nonnacked.get_age(now)
                else:
                    agenonnacked[change.id] = 0

            query.run(querycb)

        compound = ReportOutputCompound()
        summary = ReportOutputList([
            ReportOutputColumn("nreviews", "Total open reviews", format="%d",
                               mapfunc=lambda rep, col, row: row[0] + row [1]),
            ReportOutputColumn("waitsubmitter", "Waiting on submitter", format="%d",
                               mapfunc=lambda rep, col, row: row[0]),
            ReportOutputColumn("waitreviewer", "Waiting on reviewer", format="%d",
                               mapfunc=lambda rep, col, row: row[1]),
        ], title="Review summary")
        summary.set_row([len(wait_submitter), len(wait_reviewer)])
        compound.add_report(summary)

        lastrev = ReportOutputList([
            ReportOutputColumn("average", "Average wait time",
                               mapfunc=lambda rep, col, row: row[0]),
            ReportOutputColumn("median", "Median wait time",
                               mapfunc=lambda rep, col, row: row[1]),
            ReportOutputColumn("stale", "Older than %d days" % self.days, format="%d",
                               mapfunc=lambda rep, col, row: row[2]),
        ], title="Summary since current revision")
        lastrev.set_row([self.average_age(wait_reviewer, agecurrent),
                         self.median_age(wait_reviewer, agecurrent),
                         self.older_than(wait_reviewer, agecurrent, self.days)])
        compound.add_report(lastrev)


        firstrev = ReportOutputList([
            ReportOutputColumn("average", "Average wait time",
                               mapfunc=lambda rep, col, row: row[0]),
            ReportOutputColumn("median", "Median wait time",
                               mapfunc=lambda rep, col, row: row[1]),
        ], title="Summary since first revision")
        firstrev.set_row([self.average_age(wait_reviewer, agefirst),
                          self.median_age(wait_reviewer, agefirst)])
        compound.add_report(firstrev)


        nonnackedrev = ReportOutputList([
            ReportOutputColumn("average", "Average wait time",
                               mapfunc=lambda rep, col, row: row[0]),
            ReportOutputColumn("median", "Median wait time",
                               mapfunc=lambda rep, col, row: row[1]),
        ], title="Summary since last revision without -1/-2 from reviewer")
        nonnackedrev.set_row([self.average_age(wait_reviewer, agenonnacked),
                              self.median_age(wait_reviewer, agenonnacked)])
        compound.add_report(nonnackedrev)


        def waitlastmap(rep, col, row):
            return format_delta(row.get_current_age())

        def waitlastsort(rep, col, row):
            return row.get_current_age()

        waitlastrev = self.new_table("Longest waiting since current revision")
        waitlastrev.add_column(ReportOutputColumn("age", "Age",
                                                  sortfunc=waitlastsort,
                                                  mapfunc=waitlastmap))
        waitlastrev.sortcol = "age"
        waitlastrev.reverse = True
        for change in self.get_longest_changes(wait_reviewer, changes, agecurrent, 5):
            waitlastrev.add_row(change)
        compound.add_report(waitlastrev)


        def waitfirstmap(rep, col, row):
            return format_delta(row.get_first_age())

        def waitfirstsort(rep, col, row):
            return row.get_first_age()

        waitfirstrev = self.new_table("Longest waiting since first revision")
        waitfirstrev.add_column(ReportOutputColumn("age", "Age",
                                                   sortfunc=waitfirstsort,
                                                   mapfunc=waitfirstmap))
        waitfirstrev.sortcol = "age"
        waitfirstrev.reverse = True
        for change in self.get_longest_changes(wait_reviewer, changes, agefirst, 5):
            waitfirstrev.add_row(change)
        compound.add_report(waitfirstrev)


        def waitnonnackedmap(rep, col, row):
            return format_delta(row.get_reviewer_not_nacked_age())

        def waitnonnackedsort(rep, col, row):
            return row.get_reviewer_not_nacked_age()

        waitnonnackedrev = self.new_table("Longest waiting since last revision without -1/-2 from reviewer")
        waitnonnackedrev.add_column(ReportOutputColumn("age", "Age",
                                                       sortfunc=waitnonnackedsort,
                                                       mapfunc=waitnonnackedmap))
        waitnonnackedrev.sortcol = "age"
        waitnonnackedrev.reverse = True
        for change in self.get_longest_changes(wait_reviewer, changes, agenonnacked, 5):
            waitnonnackedrev.add_row(change)
        compound.add_report(waitnonnackedrev)

        return compound
