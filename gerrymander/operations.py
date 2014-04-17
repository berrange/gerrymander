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

from gerrymander.model import ModelChange
from gerrymander.model import ModelEvent


class OperationBase(object):

    def __init__(self, client):
        self.client = client


class OperationQuery(OperationBase):
    PATCHES_NONE = "none"
    PATCHES_CURRENT = "current"
    PATCHES_ALL = "all"

    STATUS_SUBMITTED = "submitted"
    STATUS_REVIEWED = "reviewed"
    STATUS_MERGED = "merged"
    STATUS_ABANDONED = "abandoned"
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"

    def __init__(self, client, terms={}, rawquery=None, patches=PATCHES_NONE,
                 approvals=False, files=False, comments=False):
        OperationBase.__init__(self, client)
        self.terms = terms
        self.rawquery = rawquery
        self.patches = patches
        self.approvals = approvals
        self.files = files
        self.comments = comments

        if self.patches == OperationQuery.PATCHES_NONE:
            if self.approvals:
                raise Exception("approvals cannot be requested without patches")
            if self.files:
                raise Exception("files cannot be requested without patches")

    def get_args(self, limit=None, sortkey=None):
        args = ["query", "--format=JSON"]
        if self.patches == OperationQuery.PATCHES_CURRENT:
            args.append("--current-patch-set")
        elif self.patches == OperationQuery.PATCHES_ALL:
            args.append("--patch-sets")

        if self.approvals:
            args.append("--all-approvals")
        if self.files:
            args.append("--files")
        if self.comments:
            args.append("--comments")

        clauses = []
        if limit is not None:
            clauses.append("limit:" + str(limit))
        if sortkey is not None:
            clauses.append("resume_sortkey:" + sortkey)
        if self.rawquery is not None:
            clauses.append("(" + self.rawquery + ")")
        terms = list(self.terms.keys())
        terms.sort()
        for term in terms:
            negateAll = False
            terms = self.terms[term]
            if len(terms) > 0 and terms[0] == "!":
                negateAll = True
                terms = terms[1:]

            if len(terms) == 0:
                continue

            subclauses = []
            for value in terms:
                subclauses.append("%s:%s" % (term, value))

            clause = " OR ".join(subclauses)
            if negateAll:
                clause = "( NOT ( " + clause + " ) )"
            else:
                clause = "( " + clause + " )"
            clauses.append(clause)
        args.append(" AND ".join(clauses))
        return args

    def run(self, cb, limit=None):
        class tracker(object):
            def __init__(self):
                self.gotany = True
                self.count = 0
                self.sortkey = None

        c = tracker()
        def mycb(line):
            if 'rowCount' in line:
                return
            if 'type' in line and line['type'] == "error":
                raise Exception(line['message'])

            change = ModelChange.from_json(line)
            if "sortKey" in line:
                c.sortkey = line["sortKey"]
            c.gotany = True
            c.count = c.count + 1
            cb(change)

        if limit is None:
            while c.gotany:
                c.gotany = False
                self.client.run(self.get_args(500, c.sortkey), mycb)
        else:
            while c.count < limit and c.gotany:
                want = limit - c.count
                if want > 500:
                    want = 500
                c.gotany = False
                self.client.run(self.get_args(want, c.sortkey), mycb)
        return 0


class OperationWatch(OperationBase):

    def __init__(self, client):
        OperationBase.__init__(self, client)

    def run(self, cb):
        def mycb(line):
            event = ModelEvent.from_json(line)
            if event:
                cb(event)

        return self.client.run(["stream-events"], mycb)
