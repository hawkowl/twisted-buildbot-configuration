from twisted.trial import unittest
from buildbot.status.results import SUCCESS, FAILURE
from buildbot.test.util.steps import BuildStepMixin
from buildbot.test.fake.remotecommand import ExpectShell

from txbuildbot.lint import LintStep
from txbuildbot.lint import CheckDocumentation
from txbuildbot.lint import CheckCodesByTwistedChecker, TwistedCheckerError
from txbuildbot.lint import PyFlakes, PyFlakesError


## TODO: Add tests for getLastBuild/getPreviousLog

class TestComputeDiffference(unittest.TestCase):
    """
    Tests for L{LintStep.computeDifference}.
    """

    
    def test_emptyPrevious(self):
        """
        When given an C{previous} dict that is empty, and a C{current} dict,
        C{computeDifference} returns a dictionary identical to C{current}.
        """
        current = {'stuff': set(['a', 'b']), 'other': set(['x', 'y'])}
        diff = LintStep.computeDifference(current, {})
        self.assertEqual(diff, current)

    def test_emptyCurrent(self):
        """
        When given an C{current} dict that is empty, and a C{previous} dict,
        C{computeDifference} returns an empty dict.
        """
        previous = {'stuff': set(['a', 'b']), 'other': set(['x', 'y'])}
        diff = LintStep.computeDifference({}, previous)
        self.assertEqual(diff, {})

    def test_newKey(self):
        """
        When given a C{current} dict that has a key that isn't in C{previous} dict,
        C{computeDifference} returns a dict with everything in that key.
        """
        previous = {'stuff': set(['a', 'b'])}
        current = {'stuff': set(['a', 'b']), 'other': set(['x', 'y'])}
        diff = LintStep.computeDifference(current, previous)
        self.assertEqual(diff, {'other': set(['x', 'y'])})

    def test_lessKeys(self):
        """
        When given a C{current} dict that is missing keys from C{previous},
        C{computeDifference} returns a dict with only the keys from C{current}.
        """
        current = {'stuff': set(['a', 'b'])}
        previous = {'stuff': set(['a']), 'other': set(['x', 'y'])}
        diff = LintStep.computeDifference(current, previous)
        self.assertEqual(diff, {'stuff': set(['b'])})

    def test_sameKey(self):
        """
        When given a C{current} dict with a key whose contents is identical to C{previous},
        C{computeDifference} returns a dict without that key.
        """
        current = {'stuff': set(['a', 'b'])}
        previous = {'stuff': set(['a', 'b'])}
        diff = LintStep.computeDifference(current, previous)
        self.assertEqual(diff, {})



class LintStepMixin(BuildStepMixin):
    """
    Mixin for creating a step that succeeds, and returns appropriate old and new lint text.
    """

    def setupStep(self, step, command=None, oldText='old', newText='new'):
        """
        Initializes L{BuildStepMixin} with the provided step, and sets the command to
        expect a single shell command, and 

        @type step: L{LintStep} 
        @param step: step to run

        @type oldText: L(str)
        @param oldText: Value to be returned from L{LintStep.getPreviousLog}

        @type newText: L{str}
        @param oldText: Log to be generated by remote command.

        @return: None
        """
        BuildStepMixin.setupStep(self, step)
        self.step.getPreviousLog = lambda: oldText
        self.expectCommands(
                ExpectShell(command=command or step.__class__.command, workdir='wkdir', usePTY='slave-config')
                + ExpectShell.log('stdio', stdout=newText)
                + 0
        )



class FakeLintStep(LintStep):
    """
    A minimal L{LintStep} subclass for testing.
    """

    name = 'test-lint-step'
    command = [ 'lint-command' ]
    description = [ 'lint', 'desc' ]
    descriptionDone = [ 'lint', 'done' ]
    lintChecker = 'test-lint'

    def __init__(self, oldErrors, newErrors):
        """
        @param oldErrors: errors to return when C{logText} is C{'old'}
        @param newErrors: errors to return when C{logText} is C{'new'}
        """
        LintStep.__init__(self)
        self.factory[1].clear()
        self.addFactoryArguments(oldErrors=oldErrors, newErrors=newErrors)
        self.oldErrors = oldErrors
        self.newErrors = newErrors

    def computeErrors(self, logText):
        if logText == 'old':
            return self.oldErrors
        else:
            return self.newErrors

    def formatErrors(self, newErrors):
        return ['%r' % newErrors]



class TestLintStep(LintStepMixin, unittest.TestCase):
    """
    Tests for L{LintStep}
    """

    setUp = LintStepMixin.setUpBuildStep
    tearDown = LintStepMixin.tearDownBuildStep

    def test_newErrors(self):
        """
        """
        self.setupStep(FakeLintStep(
            oldErrors={'old': set(['a', 'b', 'c']), 'new': set(['a', 'b'])},
            newErrors={'old': set(['a', 'b']), 'new': set(['a', 'b', 'c'])}))
        self.expectOutcome(result=FAILURE, status_text=['lint', 'done', 'failed'])
        self.expectLogfile('test-lint errors', '%r' % {'old': set(['a', 'b']), 'new': set(['a', 'b', 'c'])})
        self.expectLogfile('new test-lint errors', '%r' % {'new': set(['c'])})
        return self.runStep()

    def test_fixedErrors(self):
        """
        """
        self.setupStep(FakeLintStep(
            oldErrors={'old': set(['a', 'b', 'c']), 'new': set(['a', 'b'])},
            newErrors={'old': set(['a', 'b']), 'new': set(['a', 'b'])}))
        self.expectOutcome(result=SUCCESS, status_text=['lint', 'done'])
        self.expectLogfile('test-lint errors', '%r' % {'old': set(['a', 'b']), 'new': set(['a', 'b'])})
        return self.runStep()

    def test_sameErrors(self):
        """
        """
        self.setupStep(FakeLintStep(
            oldErrors={'old': set(['a', 'b', 'c']), 'new': set(['a', 'b'])},
            newErrors={'old': set(['a', 'b', 'c']), 'new': set(['a', 'b'])}))
        self.expectOutcome(result=SUCCESS, status_text=['lint', 'done'])
        self.expectLogfile('test-lint errors', '%r' % {'old': set(['a', 'b', 'c']), 'new': set(['a', 'b'])}) 
        return self.runStep()

class PydoctorTests(LintStepMixin, unittest.TestCase):
    """
    Tests for L{CheckDocumentation}
    """

    setUp = LintStepMixin.setUpBuildStep
    tearDown = LintStepMixin.tearDownBuildStep

    logText = [
        "twisted.spread.ui.tkutil:0 invalid ref to Tkinter",
        "twisted.spread.pb.CopyableFailure:404 invalid ref to flavors.RemoteCopy",
        "twisted.spread.pb.CopyableFailure:404 invalid ref to flavors.Copyable",
        "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'listdir' 'The implementation ....'>",
        "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'getpid' 'The implementation ....'>",
        "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'openfile' 'The implementation ....'>",
        ]

    def test_computeErrors(self):
        """
        When L{CheckDocumentation.computeErrors} is called  ...
        """

        errors = CheckDocumentation.computeErrors("\n".join(self.logText))
        self.assertEqual(errors, {
            'invalid ref': set([
                "twisted.spread.ui.tkutil: invalid ref to Tkinter",
                "twisted.spread.pb.CopyableFailure: invalid ref to flavors.RemoteCopy",
                "twisted.spread.pb.CopyableFailure: invalid ref to flavors.Copyable",
                ]),
            'unknown fields': set([
                "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'listdir' 'The implementation ....'>",
                "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'getpid' 'The implementation ....'>",
                "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'openfile' 'The implementation ....'>",
                ])})


    def test_newErrors(self):
        """
        """

        self.setupStep(CheckDocumentation(),
                oldText = "\n".join(self.logText[0:5:2]),
                newText = "\n".join(self.logText),
                )
        self.expectOutcome(result=FAILURE, status_text=['api', 'docs'])
        self.expectLogfile('pydoctor errors', "\n".join([
            "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'getpid' 'The implementation ....'>",
            "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'listdir' 'The implementation ....'>",
            "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'openfile' 'The implementation ....'>",
            "twisted.spread.pb.CopyableFailure: invalid ref to flavors.Copyable",
            "twisted.spread.pb.CopyableFailure: invalid ref to flavors.RemoteCopy",
            "twisted.spread.ui.tkutil: invalid ref to Tkinter",
            ]))
        self.expectLogfile('new pydoctor errors', "\n".join([
            "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'listdir' 'The implementation ....'>",
            "found unknown field on 'twisted.internet.process._FDDetector': <Field 'ivars' 'openfile' 'The implementation ....'>",
            "twisted.spread.pb.CopyableFailure: invalid ref to flavors.RemoteCopy",
            ]))
        return self.runStep()

class CheckCodesByTwistedCheckerTests(LintStepMixin, unittest.TestCase):
    """
    Tests for L{CheckCodesByTwistedChecker}
    """

    setUp = LintStepMixin.setUpBuildStep
    tearDown = LintStepMixin.tearDownBuildStep

    logText = [
        '************* Module twisted.python',
        'W9002:  1,0: Missing a reference to test module in header',
        'W9011: 12,0: Blank line contains whitespace',
        'W9402: 32,0: The first letter of comment should be capitalized',
        '************* Module twisted.python.util',
        'C0301: 19,0: Line too long (81/79)',
        '************* Module twisted.python.threadpool',
        'W9402:211,0: The first letter of comment should be capitalized',
        'C0103: 55,8:ThreadPool.__init__: Invalid name "q" (should match ((([a-z_])|([a-z]+_[a-z]))[a-zA-Z0-9]+)$)',
        'C0103: 88,8:ThreadPool.__setstate__: Invalid name "__dict__" (should match ((([a-z_])|([a-z]+_[a-z]))[a-zA-Z0-9]+)$)',
        '************* Module twisted.trial._utilpy3',
        'W9013: 28,0: Expected 3 blank lines, found 2',
        'W9013: 43,0: Expected 3 blank lines, found 2',
        'W9201: 17,0:acquireAttribute: The opening/closing of docstring should be on a line by themselves',
        'W9202: 17,0:acquireAttribute: Missing epytext markup @param for argument "objects"',
        'W9202: 17,0:acquireAttribute: Missing epytext markup @param for argument "attr"',
        '************* Module twisted.trial.test.test_test_visitor',
        'W9208:  1,0: Missing docstring',
        'W9208:  8,0:MockVisitor: Missing docstring',
        'W9208: 18,0:TestTestVisitor: Missing docstring',
        ]

    def test_coputeErrors(self):
        errors = CheckCodesByTwistedChecker.computeErrors("\n".join(self.logText))
        self.assertEqual(errors, {
            'twisted.python': set([
                TwistedCheckerError('W9002:  1,0: Missing a reference to test module in header'),
                TwistedCheckerError('W9011: 12,0: Blank line contains whitespace'),
                TwistedCheckerError('W9402: 32,0: The first letter of comment should be capitalized'),
                ]),
            'twisted.python.util': set([
                TwistedCheckerError('C0301: 19,0: Line too long (81/79)'),
                ]),
            'twisted.python.threadpool': set([
                TwistedCheckerError('W9402:211,0: The first letter of comment should be capitalized'),
                TwistedCheckerError('C0103: 55,8:ThreadPool.__init__: Invalid name "q" (should match ((([a-z_])|([a-z]+_[a-z]))[a-zA-Z0-9]+)$)'),
                TwistedCheckerError('C0103: 88,8:ThreadPool.__setstate__: Invalid name "__dict__" (should match ((([a-z_])|([a-z]+_[a-z]))[a-zA-Z0-9]+)$)'),
                ]),
            'twisted.trial._utilpy3': set([
                TwistedCheckerError('W9013: 28,0: Expected 3 blank lines, found 2'),
                TwistedCheckerError('W9013: 43,0: Expected 3 blank lines, found 2'),
                TwistedCheckerError('W9201: 17,0:acquireAttribute: The opening/closing of docstring should be on a line by themselves'),
                TwistedCheckerError('W9202: 17,0:acquireAttribute: Missing epytext markup @param for argument "objects"'),
                TwistedCheckerError('W9202: 17,0:acquireAttribute: Missing epytext markup @param for argument "attr"'),
                ]),
            'twisted.trial.test.test_test_visitor': set([
                TwistedCheckerError('W9208:  1,0: Missing docstring'),
                TwistedCheckerError('W9208:  8,0:MockVisitor: Missing docstring'),
                TwistedCheckerError('W9208: 18,0:TestTestVisitor: Missing docstring'),
                ])})

    def test_newErrors(self):
        """
        """

        self.setupStep(CheckCodesByTwistedChecker(), command=['twistedchecker', 'twisted'],
                oldText = "\n".join(self.logText[0:-1:2]),
                newText = "\n".join(self.logText),
                )
        self.expectOutcome(result=FAILURE, status_text=['check', 'results', 'failed'])
        self.expectLogfile('twistedchecker twisted.python errors', '\n'.join([
            '************* Module twisted.python',
            'W9002:  1,0: Missing a reference to test module in header',
            'W9011: 12,0: Blank line contains whitespace',
            'W9402: 32,0: The first letter of comment should be capitalized',
            '************* Module twisted.python.threadpool',
            'C0103: 55,8:ThreadPool.__init__: Invalid name "q" (should match ((([a-z_])|([a-z]+_[a-z]))[a-zA-Z0-9]+)$)',
            'C0103: 88,8:ThreadPool.__setstate__: Invalid name "__dict__" (should match ((([a-z_])|([a-z]+_[a-z]))[a-zA-Z0-9]+)$)',
            'W9402:211,0: The first letter of comment should be capitalized',
            '************* Module twisted.python.util',
            'C0301: 19,0: Line too long (81/79)',
            ]))
        self.expectLogfile('twistedchecker twisted.trial errors', '\n'.join([
            '************* Module twisted.trial._utilpy3',
            'W9201: 17,0:acquireAttribute: The opening/closing of docstring should be on a line by themselves',
            'W9202: 17,0:acquireAttribute: Missing epytext markup @param for argument "attr"',
            'W9202: 17,0:acquireAttribute: Missing epytext markup @param for argument "objects"',
            'W9013: 28,0: Expected 3 blank lines, found 2',
        #    'W9013: 43,0: Expected 3 blank lines, found 2',
            '************* Module twisted.trial.test.test_test_visitor',
            'W9208:  1,0: Missing docstring',
            'W9208:  8,0:MockVisitor: Missing docstring',
            'W9208: 18,0:TestTestVisitor: Missing docstring',
            ]))
        self.expectLogfile('new twistedchecker errors', '\n'.join([
            '************* Module twisted.python',
            'W9002:  1,0: Missing a reference to test module in header',
            'W9402: 32,0: The first letter of comment should be capitalized',
            '************* Module twisted.python.threadpool',
            'C0103: 88,8:ThreadPool.__setstate__: Invalid name "__dict__" (should match ((([a-z_])|([a-z]+_[a-z]))[a-zA-Z0-9]+)$)',
            'W9402:211,0: The first letter of comment should be capitalized',
            '************* Module twisted.python.util',
            'C0301: 19,0: Line too long (81/79)',
            '************* Module twisted.trial._utilpy3',
            'W9201: 17,0:acquireAttribute: The opening/closing of docstring should be on a line by themselves',
            'W9202: 17,0:acquireAttribute: Missing epytext markup @param for argument "attr"',
        #   'W9013: 28,0: Expected 3 blank lines, found 2',
            '************* Module twisted.trial.test.test_test_visitor',
            'W9208:  1,0: Missing docstring',
            'W9208: 18,0:TestTestVisitor: Missing docstring',
            ]))
        return self.runStep()

class PyFlakesTests(LintStepMixin, unittest.TestCase):
    """
    Tests for L{PyFlakes}
    """

    setUp = LintStepMixin.setUpBuildStep
    tearDown = LintStepMixin.tearDownBuildStep

    logText = [
        "twisted/conch/manhole_tap.py:14: 'session' imported but unused",
        "twisted/conch/manhole_tap.py:15: 'iconch' imported but unused",
        "twisted/mail/bounce.py:40: local variable 'boundary' is assigned to but never used",
        "twisted/test/test_jelly.py:571: local variable 'n11' is assigned to but never used",
        "twisted/test/test_jelly.py:572: local variable 'n2' is assigned to but never used",
        ]

    def test_coputeErrors(self):
        errors = PyFlakes.computeErrors("\n".join(self.logText))
        self.assertEqual(errors, {
            'pyflakes': set([
                PyFlakesError("twisted/conch/manhole_tap.py:14: 'session' imported but unused",
                    "twisted/conch/manhole_tap.py", "14",
                    "'session' imported but unused"),

                PyFlakesError("twisted/conch/manhole_tap.py:15: 'iconch' imported but unused",
                    "twisted/conch/manhole_tap.py", "15",
                    "'iconch' imported but unused"),
                PyFlakesError("twisted/mail/bounce.py:40: local variable 'boundary' is assigned to but never used",
                    "twisted/mail/bounce.py", "40",
                    "local variable 'boundary' is assigned to but never used"),
                PyFlakesError("twisted/test/test_jelly.py:571: local variable 'n11' is assigned to but never used",
                    "twisted/test/test_jelly.py", "571",
                    "local variable 'n11' is assigned to but never used"),
                PyFlakesError("twisted/test/test_jelly.py:572: local variable 'n2' is assigned to but never used",
                    "twisted/test/test_jelly.py", "572",
                    "local variable 'n2' is assigned to but never used"),
                ])})

    def test_newErrors(self):
        """
        """

        self.setupStep(PyFlakes(), command=['pyflakes', 'twisted'],
                oldText = "\n".join(self.logText[0:3]),
                newText = "\n".join(self.logText),
                )
        self.expectOutcome(result=FAILURE, status_text=['pyflakes', 'failed'])
        self.expectLogfile('new pyflakes errors', '\n'.join([
            "twisted/test/test_jelly.py:571: local variable 'n11' is assigned to but never used",
            "twisted/test/test_jelly.py:572: local variable 'n2' is assigned to but never used",
            ]))
        return self.runStep()

