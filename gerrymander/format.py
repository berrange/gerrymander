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

import time

def format_date(then):
    if then is None:
        return ""
    try:
        now = time.time()
        delta = now - then
        days = delta / (60 * 60 * 24)
        hours = delta / (60 * 60)
        mins = delta / 60

        if days == 1:
            return "%d day" % days
        elif days > 1:
            return "%d days" % days
        elif hours == 1:
            return "%d hour" % hours
        elif hours > 1:
            return "%d hours" % hours
        elif mins == 1:
            return "%d min" % mins
        elif mins > 1:
            return "%d mins" % mins
        else:
            return "just now"

    except (TypeError, ValueError):
        return ""
