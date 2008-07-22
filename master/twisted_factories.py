"""
Build classes specific to the Twisted codebase
"""

from buildbot.process.base import Build
from buildbot.process.factory import BuildFactory
from buildbot.scheduler import Scheduler
from buildbot.steps import shell, transfer
from buildbot.steps.shell import ShellCommand
from buildbot.steps.source import SVN, Bzr

from twisted_steps import HLint, ProcessDocs, BuildDebs, \
    Trial, RemovePYCs, CheckDocumentation
from pypy_steps import Translate

TRIAL_FLAGS = ["--reporter=bwverbose"]
WARNING_FLAGS = ["--unclean-warnings"]
FORCEGC_FLAGS = ["--force-gc"]

class TwistedBuild(Build):
    workdir = "Twisted" # twisted's bin/trial expects to live in here



class TwistedScheduler(Scheduler):
    def fileIsImportant(self, change):
        for filename in change.files:
            if not filename.startswith("doc/fun/"):
                return 1
        return 0



class TwistedTrial(Trial):
    tests = "twisted"
    # the Trial in Twisted >=2.1.0 has --recurse on by default, and -to
    # turned into --reporter=bwverbose .
    recurse = False
    trialMode = TRIAL_FLAGS
    testpath = None
    trial = "./bin/trial"

class TwistedBaseFactory(BuildFactory):
    buildClass = TwistedBuild
    # bin/trial expects its parent directory to be named "Twisted": it uses
    # this to add the local tree to PYTHONPATH during tests
    workdir = "Twisted"

    forceGarbageCollection = False

    def __init__(self, source, uncleanWarnings, trialMode=None):
        BuildFactory.__init__(self, [source])
        self.uncleanWarnings = uncleanWarnings
        self.trialMode = trialMode

    def addTrialStep(self, **kw):
        if self.trialMode is not None:
            trialMode = self.trialMode
        else:
            trialMode = TRIAL_FLAGS

        if self.uncleanWarnings:
            trialMode = trialMode + WARNING_FLAGS
        if self.forceGarbageCollection:
            trialMode = trialMode + FORCEGC_FLAGS
        self.addStep(TwistedTrial, trialMode=trialMode, **kw)


class QuickTwistedBuildFactory(TwistedBaseFactory):
    treeStableTimer = 30
    useProgress = 0

    def __init__(self, source, python="python", uncleanWarnings=True):
        TwistedBaseFactory.__init__(self, source, uncleanWarnings)
        if type(python) is str:
            python = [python]
        self.addStep(HLint, python=python[0])
        self.addStep(RemovePYCs)
        for p in python:
            cmd = [p, "setup.py", "build_ext", "-i"]
            self.addStep(shell.Compile, command=cmd, flunkOnFailure=True)
            self.addTrialStep(python=p, testChanges=True)



class TwistedDocumentationBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5 * 60

    def __init__(self, source, python="python"):
        TwistedBaseFactory.__init__(self, source, False)
        self.addStep(CheckDocumentation)
        self.addStep(ProcessDocs)



class FullTwistedBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5*60

    def __init__(self, source, python="python",
                 runTestsRandomly=False,
                 compileOpts=[], compileOpts2=[],
                 uncleanWarnings=True, trialMode=None):
        TwistedBaseFactory.__init__(self, source, uncleanWarnings, trialMode=trialMode)

        if type(python) == str:
            python = [python]
        assert isinstance(compileOpts, list)
        assert isinstance(compileOpts2, list)
        cmd = (python + compileOpts + ["setup.py", "build_ext"]
               + compileOpts2 + ["-i"])

        self.addStep(shell.Compile, command=cmd, flunkOnFailure=True)
        self.addStep(RemovePYCs)
        self.addTrialStep(python=python, randomly=runTestsRandomly)


class TwistedDebsBuildFactory(TwistedBaseFactory):
    treeStableTimer = 10*60

    def __init__(self, source, python="python"):
        TwistedBaseFactory.__init__(self, source)
        self.addStep(ProcessDocs, haltOnFailure=True)
        self.addStep(BuildDebs, warnOnWarnings=True)


class Win32RemovePYCs(ShellCommand):
    name = "remove-.pyc"
    command = 'del /s *.pyc'
    description = ["removing", ".pyc", "files"]
    descriptionDone = ["remove", ".pycs"]


class GoodTwistedBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5 * 60

    forceGarbageCollection = True

    def __init__(self, source, python="python",
                 processDocs=False, runTestsRandomly=False,
                 compileOpts=[], compileOpts2=[],
                 uncleanWarnings=True):
        TwistedBaseFactory.__init__(self, source, uncleanWarnings)
        if processDocs:
            self.addStep(ProcessDocs)

        if type(python) == str:
            python = [python]
        assert isinstance(compileOpts, list)
        assert isinstance(compileOpts2, list)
        cmd = (python + compileOpts + ["setup.py", "build_ext"]
               + compileOpts2 + ["-i"])

        self.addStep(shell.Compile, command=cmd, flunkOnFailure=True)
        self.addStep(RemovePYCs)
        self.addTrialStep(python=python, randomly=runTestsRandomly)


class TwistedReactorsBuildFactory(TwistedBaseFactory):
    treeStableTimer = 5*60

    def __init__(self, source, RemovePYCs=RemovePYCs,
                 python="python", compileOpts=[], compileOpts2=[],
                 reactors=["select"], uncleanWarnings=True):
        TwistedBaseFactory.__init__(self, source, uncleanWarnings)

        if type(python) == str:
            python = [python]
        assert isinstance(compileOpts, list)
        assert isinstance(compileOpts2, list)
        cmd = (python + compileOpts + ["setup.py", "build_ext"]
               + compileOpts2 + ["-i"])

        self.addStep(shell.Compile, command=cmd, warnOnFailure=True)

        for reactor in reactors:
            self.addStep(RemovePYCs)
            self.addTrialStep(
                name=reactor, python=python,
                reactor=reactor, flunkOnFailure=True,
                warnOnFailure=False)


class TwistedEasyInstallFactory(TwistedBaseFactory):
    treeStableTimer = 5*60

    def __init__(self, source, uncleanWarnings, python="python",
                 reactor="epoll", easy_install="easy_install"):
        TwistedBaseFactory.__init__(self, source, uncleanWarnings)
        if type(python) == str:
            python = [python]


        setupCommands = [
            ["rm", "-rf", "install"],
            ["mkdir", "-p", "install/bin", "install/lib"],
            [easy_install, "--install-dir", "install/lib",
                           "--script-dir", "install/bin",
                           "."],
            ]
        for command in setupCommands:
            self.addStep(shell.ShellCommand, command=command,
                         env={"PYTHONPATH": "install/lib"},
                         haltOnFailure=True)
        self.addTrialStep(
            name=reactor, python=python,
            reactor=reactor, flunkOnFailure=True,
            warnOnFailure=False, workdir="Twisted/install",
            env={"PYTHONPATH": "lib"})



class PyPyTranslationFactory(BuildFactory):
    def __init__(self, translationArguments, targetArguments, *a, **kw):
        BuildFactory.__init__(self, *a, **kw)

        self.addStep(
            SVN,
            workdir="build/pypy-src",
            baseURL="http://codespeak.net/svn/pypy/",
            defaultBranch="dist",
            mode="copy")
        self.addStep(
            Translate,
            translationArgs=translationArguments,
            targetArgs=targetArguments)



class TwistedPyPyBuildFactory(BuildFactory):
    def __init__(self, *a, **kw):
        BuildFactory.__init__(self, *a, **kw)
        self.addStep(
            SVN,
            workdir="build/Twisted-src",
            svnurl="svn://svn.twistedmatrix.com/svn/Twisted/trunk",
            mode="copy")
        self.addStep(
            Trial,
            workdir="build/pypy-src/pypy/translator/goal",
            python=["pypy-c"],
            testpath=None,
            trial="../../../../Twisted-src/bin/trial",
            tests=["twisted"],
            env={"PATH": "/usr/bin:."})



class PyOpenSSLBuildFactoryBase(BuildFactory):
    """
    Build and test PyOpenSSL.
    """
    currentPyOpenSSLVersion = "0.7"

    def __init__(self, versions):
        BuildFactory.__init__(self, [])
        self.uploadBase = 'public_html/builds/'
        self.addStep(
             Bzr,
             baseURL="http://bazaar.launchpad.net/~exarkun/pyopenssl/",
             defaultBranch="trunk",
             mode="copy")



class LinuxPyOpenSSLBuildFactory(PyOpenSSLBuildFactoryBase):
    """
    Build and test a Linux (or Linux-like) PyOpenSSL package.
    """
    def trial(self, version):
        """
        Return the path to the trial script for the given version of
        Python.
        """
        return "/usr/bin/trial"


    def platform(self, version):
        return self._platform


    def python(self, version):
        return "python" + version


    def binaryFilename(self, version):
        """
        Return the basename of the output of the I{bdist} command of
        distutils for the given version of Python.
        """
        return (
            'pyOpenSSL-' + self.currentPyOpenSSLVersion + '.' +
            self.platform(version) + '.tar.gz')


    def binaryUploadFilename(self, version):
        return 'pyOpenSSL-dev.py%s.%s.tar.gz' % (
            version, self.platform(version))


    def __init__(self, versions, source, platform=None):
        PyOpenSSLBuildFactoryBase.__init__(self, [])
        self._platform = platform
        if source:
            self.addStep(
                shell.Compile,
                # Doesn't matter what Python gets used for sdist
                command=["python", "setup.py", "sdist"],
                flunkOnFailure=True)
            self.addStep(
                transfer.FileUpload,
                slavesrc=(
                    'dist/pyOpenSSL-' + self.currentPyOpenSSLVersion +
                    '.tar.gz'),
                masterdest=self.uploadBase + 'pyOpenSSL-dev.tar.gz')
        for pyVersion in versions:
            python = self.python(pyVersion)
            self.addStep(
                shell.Compile,
                command=[python, "setup.py", "bdist"],
                flunkOnFailure=True)
            self.addStep(
                Trial,
                workdir="build/build/lib.%s-%s" % (self.platform(pyVersion), pyVersion),
                python=python,
                trial=self.trial(pyVersion),
                tests="OpenSSL",
                testpath=None)
            self.addStep(
                transfer.FileUpload,
                slavesrc='dist/' + self.binaryFilename(pyVersion),
                masterdest=(self.uploadBase + '/' +
                            self.binaryUploadFilename(pyVersion)))



class DebianPyOpenSSLBuildFactory(LinuxPyOpenSSLBuildFactory):
    """
    Build and test a Debian (or Debian-derivative) PyOpenSSL package.
    """
    def __init__(self, versions, source, platform, distro, packageFiles):
        LinuxPyOpenSSLBuildFactory.__init__(self, versions, source, platform)
        self.addStep(
            shell.ShellCommand,
            command=["cp", "-a", distro, "debian"])
        self.addStep(
            shell.ShellCommand,
            command=["fakeroot", "make", "-f", "debian/rules", "binary"])
        for fileName in packageFiles:
            self.addStep(
                transfer.FileUpload,
                slavesrc="../" + fileName,
                masterdest=self.uploadBase + fileName)



class OSXPyOpenSSLBuildFactory(LinuxPyOpenSSLBuildFactory):
    """
    Build and test an OS-X PyOpenSSL package.
    """
    def trial(self, version):
        """
        Return the path to the trial script in the framework.
        """
        if version == "2.5":
            # Neutron doesn't have this.
            return "/Library/Frameworks/Python.framework/Versions/2.5/bin/trial"
        elif version == "2.4":
            return "/Library/Frameworks/Python.framework/Versions/2.4/bin/trial"
        elif version == "2.3":
            return "/System/Library/Frameworks/Python.framework/Versions/2.3/bin/trial"
        else:
            raise ValueError("Unknown Python version")


    def platform(self, version):
        if version == "2.5":
            return "macosx-10.5-ppc"
        elif version == "2.4":
            return "macosx-10.5-fat"



class Win32PyOpenSSLBuildFactory(PyOpenSSLBuildFactoryBase):
    """
    Build and test a Win32 PyOpenSSL package.
    """
    def python(self, pyVersion):
        return (
            "c:\\python%s\\python.exe" % (
                pyVersion.replace('.', ''),))


    def __init__(self, platform, compiler, pyVersion):
        PyOpenSSLBuildFactoryBase.__init__(self, [])
        python = self.python(pyVersion)
        self.addStep(
            shell.Compile,
            command=[python, "setup.py", "build_ext", "--compiler", compiler],
            flunkOnFailure=True)
        self.addStep(
            shell.Compile,
            command=[python, "setup.py", "bdist"],
            flunkOnFailure=True)
        self.addStep(
            transfer.FileUpload,
            slavesrc='dist/pyOpenSSL-' + self.currentPyOpenSSLVersion + '.win32.zip',
            masterdest=self.uploadBase + 'pyOpenSSL-dev.%s-py%s.zip' % (platform, pyVersion))
        self.addStep(
            shell.Compile,
            command=[python, "setup.py", "bdist_wininst"],
            flunkOnFailure=True)
        self.addStep(
            transfer.FileUpload,
            slavesrc='dist/pyOpenSSL-' + self.currentPyOpenSSLVersion + '.win32-py' + pyVersion + '.exe',
            masterdest=self.uploadBase + 'pyOpenSSL-dev.%s-py%s.exe' % (platform, pyVersion))
        if pyVersion >= "2.5":
            self.addStep(
                shell.Compile,
                command=[python, "setup.py", "bdist_msi"],
                flunkOnFailure=True)
            self.addStep(
                transfer.FileUpload,
                slavesrc='dist/pyOpenSSL-' + self.currentPyOpenSSLVersion + '.win32-py' + pyVersion + '.msi',
                masterdest=self.uploadBase + 'pyOpenSSL-dev.%s-py%s.msi' % (platform, pyVersion))
