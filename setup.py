
from setuptools import setup
from setuptools import Command
from distutils.command.build import build
from distutils.util import get_platform

import sys
import os
import re
import time

class my_build(build):
    user_options = build.user_options

    description = "build everything needed to install"

    def gen_rpm_spec(self):
        f1 = open('gerrymander.spec.in', 'r')
        f2 = open('gerrymander.spec', 'w')
        for line in f1:
            f2.write(line
                     .replace('@PY_VERSION@', self.distribution.get_version()))
        f1.close()
        f2.close()

    def gen_authors(self):
        f = os.popen("git log --pretty=format:'%aN <%aE>'")
        authors = []
        for line in f:
            authors.append("   " + line.strip())

        authors.sort(key=str.lower)

        f1 = open('AUTHORS.in', 'r')
        f2 = open('AUTHORS', 'w')
        for line in f1:
            f2.write(line.replace('@AUTHORS@', "\n".join(set(authors))))
        f1.close()
        f2.close()


    def gen_changelog(self):
        f1 = os.popen("git log '--pretty=format:%H:%ct %an  <%ae>%n%n%s%n%b%n'")
        f2 = open("ChangeLog", 'w')

        for line in f1:
            m = re.match(r'([a-f0-9]+):(\d+)\s(.*)', line)
            if m:
                t = time.gmtime(int(m.group(2)))
                f2.write("%04d-%02d-%02d %s\n" % (t.tm_year, t.tm_mon, t.tm_mday, m.group(3)))
            else:
                if re.match(r'Signed-off-by', line):
                    continue
                f2.write("    " + line.strip() + "\n")

        f1.close()
        f2.close()


    def run(self):
        if not os.path.exists("build"):
            os.mkdir("build")

        if os.path.exists(".git"):
            try:
                self.gen_rpm_spec()
                self.gen_authors()
                self.gen_changelog()

                build.run(self)

            except:
                files = ["gerrymander.spec",
                         "AUTHORS",
                         "ChangeLog"]
                for f in files:
                    if os.path.exists(f):
                        os.unlink(f)
        else:
            build.run(self)


class my_test(Command):
    user_options = [
        ('build-base=', 'b',
         "base directory for build library"),
        ('build-platlib=', None,
         "build directory for platform-specific distributions"),
        ('plat-name=', 'p',
         "platform name to build for, if supported "
         "(default: %s)" % get_platform()),
    ]

    description = "Run test suite."

    def initialize_options(self):
        self.build_base = 'build'
        self.build_platlib = None
        self.plat_name = None

    def finalize_options(self):
        if self.plat_name is None:
            self.plat_name = get_platform()

        plat_specifier = ".%s-%s" % (self.plat_name, sys.version[0:3])

        if hasattr(sys, 'gettotalrefcount'):
            plat_specifier += '-pydebug'

        if self.build_platlib is None:
            self.build_platlib = os.path.join(self.build_base,
                                              'lib' + plat_specifier)

    def run(self):
        """
        Run test suite
        """

        if "PYTHONPATH" in os.environ:
            os.environ["PYTHONPATH"] = self.build_platlib + ":" + os.environ["PYTHONPATH"]
        else:
            os.environ["PYTHONPATH"] = self.build_platlib
        self.spawn([sys.executable, "/usr/bin/nosetests"])


setup(
    name="gerrymander",
    version="1.4",
    description="A client API and command line tool for gerrit",
    long_description="Gerrymander provides a set of APIs and command "
    "line tool for interacting with the gerrit code review system",
    author="Daniel P. Berrange",
    author_email="dan-gerrymander@berrange.com",
    license="ASL 2.0",
    url="https://github.com/berrange/gerrymander",
    scripts=([
        "scripts/gerrymander",
        ]),
    packages=["gerrymander"],
    install_requires=["prettytable>=0.5"],
    cmdclass = {
          'build': my_build,
          'test': my_test
    },
)
