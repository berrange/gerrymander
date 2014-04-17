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
        return format_delta(delta)
    except (TypeError, ValueError):
        return ""

def format_delta(delta):
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


STYLES = {
    "reset": 0,
    "bold": 1,
    "underline": 4,
    "blinkslow": 5,
    "blinkfast": 6,
    "reverse": 7
}

COLORS = {
    "grey": 0,
    "red": 1,
    "green": 2,
    "yellow": 3,
    "blue": 4,
    "magenta": 5,
    "cyan": 6,
    "white": 7
}

FOREGROUND = 30
BACKGROUND = 40

ESCAPE = '\033[%dm'


def format_color(text, usecolor=True, fg=None, bg=None, styles=[]):
    if not usecolor:
        return text

    bits = []
    if fg is not None:
        if fg not in COLORS:
            raise Exception("Unknown color %s" % fg)
        bits.append(ESCAPE % (FOREGROUND + COLORS[fg]))
    if bg is not None:
        if bg not in COLORS:
            raise Exception("Unknown color %s" % bg)
        bits.append(ESCAPE % (BACKGROUND + COLORS[bg]))
    for style in styles:
        if style not in STYLES:
            raise Exception("Unknown style %s" % style)
        bits.append(ESCAPE % (STYLES[style]))
    bits.append(text)
    bits.append(ESCAPE % STYLES["reset"])
    return "".join(bits)


def format_title(text):
    width = len(text)
    underline = "-" * width
    return text + "\n" + underline + "\n"
