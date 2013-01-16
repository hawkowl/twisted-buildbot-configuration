from twisted.python import log, util
from buildbot.status.builder import FAILURE
from buildbot.steps.shell import ShellCommand

try:
    import cStringIO
    StringIO = cStringIO
except ImportError:
    import StringIO
import re

class LintStep(ShellCommand):
    """
    A L{ShellCommand} that generates summary information of errors generated
    during a build, and new errors generated vs. the most recent trunk build.
    
    @ivar worse: a L{bool} indicating whether this build is worse with respect
        to reported errors than the most recent trunk build.
    """

    def createSummary(self, logObj):
        logText = logObj.getText()
        self.worse = self.processLogs(self.getPreviousLog(), logText)


    def processLogs(self, oldText, newText):
        currentErrors = self.computeErrors(newText)
        previousErrors = self.computeErrors(oldText)

        self.addCompleteLog('%s errors' % self.lintChecker, '\n'.join(self.formatErrors(currentErrors)))
        self.formatErrors(previousErrors)

        newErrors = self.computeDifference(currentErrors, previousErrors)

        if newErrors:
            allNewErrors = self.formatErrors(newErrors)
            self.addCompleteLog('new %s errors' % self.lintChecker, '\n'.join(allNewErrors))

        return bool(newErrors)


    def computeErrors(self, logText):
        """
        @type logText: L{str}
        @param logText: output of lint command

        @return: L{dict} of L{set}s containing errors generated by lint, grouped by
            type
        """
        raise NotImplementedError("Must implement computeErrors for a Lint step")


    def formatErrors(self, newErrors):
        raise NotImplementedError("Must implement formatErrors for a Lint step")


    @staticmethod
    def computeDifference(current, previous):
        """
        Takes two dicts of sets, and computes the keywise difference.

        @type current: L{dict} of L{set}s
        @param current: errors from current build

        @type previous: L{dict} of L{set}s
        @param previous: errors from previous build

        @return
        @rtype L{dict}
        """
        new = {}
        for errorType in current:
            errors = (
                current[errorType] - 
                previous.get(errorType, set()))
            log.msg("Found %d new errors of type %s" % (len(errors), errorType))
            if errors:
                new[errorType] = errors
        return new


    def getPreviousLog(self):
        """
        Gets the output of lint from the last build of trunk.

        @return: output of lint from last trunk build
        @rtype: L{str}
        """
        build = self._getLastBuild()
        if build is None:
            log.msg("Found no previous build, returning empty error log")
            return ""
        for logObj in build.getLogs():
            if logObj.name == '%s errors' % self.lintChecker:
                text = logObj.getText()
                log.msg("Found error log, returning %d bytes" % (len(text),))
                return text
        log.msg("Did not find error log, returning empty error log")
        return ""


    def _getLastBuild(self):
        """
        Gets the L{BuildStatus} object of the most recent build of trunk.

        @return: most recent build of trunk
        @rtype: L{BuildStatus}
        """
        status = self.build.build_status
        number = status.getNumber()
        if number == 0:
            log.msg("last result is undefined because this is the first build")
            return None
        builder = status.getBuilder()
        for i in range(1, 11):
            build = builder.getBuild(number - i)
            if not build:
                continue
            branch = build.getProperty("branch")
            if not branch:
                log.msg("Found build on default branch at %d" % (number - i,))
                return build
            else:
                log.msg("skipping build-%d because it is on branch %r" % (i, branch))
        log.msg("falling off the end")
        return None


    def evaluateCommand(self, cmd):
        if self.worse:
            return FAILURE
        return ShellCommand.evaluateCommand(self, cmd)



class CheckDocumentation(LintStep):
    """
    Run Pydoctor over the source to check for errors in API
    documentation.
    """
    name = 'api-documentation'
    command = (
        'python '
        '~/Projects/pydoctor/trunk/bin/pydoctor '
        '--quiet '
        '--introspect-c-modules '
        '--make-html '
        '--system-class pydoctor.twistedmodel.TwistedSystem '
        '--add-package `pwd`/twisted')
    description = ["checking", "api", "docs"]
    descriptionDone = ["api", "docs"]

    lintChecker = 'pydoctor'

    @staticmethod
    def computeErrors(logText):
        errors = {}
        for line in StringIO.StringIO(logText):
            # Mostly get rid of the trailing \n
            line = line.strip()
            if 'invalid ref to' in line:
                key = 'invalid ref'
                # Discard the line number since it's pretty unstable
                # over time
                fqpnlineno, rest = line.split(' ', 1)
                fqpn, lineno = fqpnlineno.split(':')
                value = '%s: %s' % (fqpn, rest)
            elif 'found unknown field on' in line:
                key = 'unknown fields'
                value = line
            else:
                continue
            errors.setdefault(key, set()).add(value)
        return errors


    def formatErrors(self, newErrors):
        allNewErrors = []
        for errorType in newErrors:
            allNewErrors.extend(newErrors[errorType])
        allNewErrors.sort()
        return allNewErrors


    def getText(self, cmd, results):
        if results == FAILURE:
            return ["api", "docs"]
        return ShellCommand.getText(self, cmd, results)


class TwistedCheckerError(util.FancyEqMixin, object):
    regex = re.compile(r"^(?P<type>[WCEFR]\d{4}):(?P<line>\s*\d+),(?P<indent>\d+):(?P<text>.*)")
    compareAttributes = ('type', 'text')

    def __init__(self, msg):
        self.msg = msg
        m = self.regex.match(msg)
        if m:
            d = m.groupdict()
            self.type = d['type']
            self.line = d['line']
            self.indent = d['indent']
            self.text = d['text']
        else:
            self.type = "UXXXX"
            self.line = "9999"
            self.indent = "9"
            self.text = "Unparseable"
            log.err(Exception, "unparseable")

    def __hash__(self):
        return hash((self.type, self.text))

    def __str__(self):
        return self.msg

    def __cmp__(self, other):
        return cmp(
                (self.line, self.indent, self.type, self.text),
                (other.line, other.indent, other.type, other.text),
                )

    def __repr__(self):
        return ("<TwistedCheckerError type=%s line=%d indent=%d, text=%r>" %
            (self.type, int(self.line), int(self.indent), self.text))


class CheckCodesByTwistedChecker(LintStep):
    """
    Run TwistedChecker over source codes to check for new warnings
    involved in the lastest build.
    """
    name = 'run-twistedchecker'
    command = ('twistedchecker twisted')
    description = ["checking", "codes"]
    descriptionDone = ["check", "results"]
    prefixModuleName = "************* Module "
    regexLineStart = "^[WCEFR]\d{4}\:"

    lintChecker = 'twistedchecker'


    @classmethod
    def computeErrors(cls, logText):
        warnings = {}
        currentModule = None
        warningsCurrentModule = []
        for line in StringIO.StringIO(logText):
            # Mostly get rid of the trailing \n
            line = line.strip("\n")
            if line.startswith(cls.prefixModuleName):
                # Save results for previous module
                if currentModule:
                    warnings[currentModule] = set(map(TwistedCheckerError, warningsCurrentModule))
                # Initial results for current module
                moduleName = line.replace(cls.prefixModuleName, "")
                currentModule = moduleName
                warningsCurrentModule = []
            elif re.search(cls.regexLineStart, line):
                warningsCurrentModule.append(line)
            else:
                if warningsCurrentModule:
                    warningsCurrentModule[-1] += "\n" + line
                else:
                    log.msg("Bad result format for %s" % currentModule)
        # Save warnings for last module
        if currentModule:
            warnings[currentModule] = set(map(TwistedCheckerError, warningsCurrentModule))
        return warnings


    @classmethod
    def formatErrors(cls, newErrors):
        allNewErrors = []
        for modulename in sorted(newErrors.keys()):
            allNewErrors.append(cls.prefixModuleName + modulename)
            allNewErrors.extend(sorted(newErrors[modulename]))
        return map(str, allNewErrors)

    def processLogs(self, oldText, newText):
        currentErrors = self.computeErrors(newText)
        previousErrors = self.computeErrors(oldText)

        import itertools
        for toplevel, modules in itertools.groupby(sorted(currentErrors.keys()), lambda k: ".".join(k.split(".")[0:2])):
            modules = list(modules)
            self.addCompleteLog("%s %s errors" % (self.lintChecker, toplevel),
                    '\n'.join(self.formatErrors(dict([(module, currentErrors[module]) for module in modules]))))
        #self.addCompleteLog('%s errors' % self.lintChecker, '\n'.join(self.formatErrors(currentErrors)))
        self.formatErrors(previousErrors)

        newErrors = self.computeDifference(currentErrors, previousErrors)

        if newErrors:
            allNewErrors = self.formatErrors(newErrors)
            self.addCompleteLog('new %s errors' % self.lintChecker, '\n'.join(allNewErrors))

        return bool(newErrors)
