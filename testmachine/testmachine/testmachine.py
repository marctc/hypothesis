from .operations import (
    ChooseFrom,
)
import traceback
import argparse
from .context import (
    TestMachineError, RunContext
)
import os


class NoFailingProgram(TestMachineError):
    pass


class TestMachine(object):
    def __init__(
        self,
        n_iters=500,
        prog_length=200,
        good_enough=10,
        print_output=True,
        simulation=False,
        verbose=False,
        fork=False,
    ):
        self.verbose = verbose
        self.fork = fork
        self.languages = []
        self.n_iters = n_iters
        self.prog_length = prog_length
        self.good_enough = good_enough
        self.print_output = print_output
        self.simulation = simulation

    def inform(self, message):
        if self.print_output:
            print(message)

    def maybe_print_exc(self):
        if self.verbose:
            traceback.print_exc()

    def __repr__(self):
        return "TestMachine()"

    def main(self, args=None):
        parser = argparse.ArgumentParser(description='Run a testmachine')
        parser.add_argument(
            '--trial-run', help="Generate a single example program and exit",
            action="store_true", default=False
        )
        parser.add_argument(
            '--simulation', help="Don't actually execute any operations",
            action="store_true", default=self.simulation
        )
        parser.add_argument(
            '--verbose',
            help="Don't suppress errors during test case generation",
            action="store_true", default=self.verbose
        )
        parser.add_argument(
            '--fork', help="Run tests in a subprocess",
            action="store_true", default=self.fork
        )
        parser.add_argument(
            "-p", "--program-length",
            type=int, default=self.prog_length,
            help="Size of programs to generate",
        )
        parser.add_argument(
            "-i", "--iterations",
            type=int, default=self.n_iters,
            help="Number of iterations to run",
        )

        results = parser.parse_args(args)
        self.prog_length = results.program_length
        self.simulation = results.simulation
        self.fork = results.fork
        self.verbose = results.verbose
        if results.trial_run:
            self.trial_run()
        else:
            self.n_iters = results.iterations
            self.run()

    def print_execution_log(self, context):
        for step in context.log:
            statements = step.operation.compile(
                arguments=step.arguments, results=step.definitions
            )
            for statement in statements:
                self.inform(statement)

    def trial_run(self):
        context = RunContext(simulation=self.simulation)
        try:
            for _ in xrange(self.prog_length):
                operation = self.language.generate_from(context)
                context.execute(operation)
        finally:
            self.print_execution_log(context)

    def print_program_results(self, program):
        if self.fork:
            pid = os.fork()
            if pid:
                os.waitpid(pid, 0)
                return
            else:
                self.fork = False
                try:
                    self.print_program_results(program)
                finally:
                    os._exit(0)

        context = RunContext(simulation=True)
        try:
            context.run_program(program)
        except Exception:
            self.maybe_print_exc()
        self.print_execution_log(context)
        try:
            RunContext().run_program(program)
            assert False, "This program should be failing but isn't"
        except Exception:
            traceback.print_exc()

    def run(self):
        """
        run this testmachine and return a minimal failing program, or None if
        no such program can be found.

        If self.print_output is True then this will print a nice representation
        of the group to stdout and the exception generated by the failure.
        """
        try:
            first_try = self.find_failing_program()
        except NoFailingProgram as e:
            self.inform(str(e))
            return

        minimal = self.minimize_failing_program(first_try)

        if self.print_output:
            self.print_program_results(minimal)

        return minimal

    def add(self, *languages):
        self.languages.extend(languages)

    @property
    def language(self):
        return ChooseFrom(self.languages)

    def generate_program(self):
        context = RunContext(simulation=True)
        results = []
        for _ in xrange(self.prog_length):
            operation = self.language.generate_from(context)
            context.execute(operation)
            results.append(operation)
        return results

    def program_fails(self, program):
        if self.fork:
            pid = os.fork()
            if pid:
                pid, status = os.waitpid(pid, 0)
                return status != 0
            else:
                try:
                    self.run_program(program)
                except:
                    self.maybe_print_exc()
                    os._exit(1)
                os._exit(0)
        else:
            try:
                self.run_program(program)
                return False
            except Exception:
                return True

    def find_failing_initial_segment(self, program):
        low = 0
        high = len(program)

        # invariant: program[:high] fails, program[:low] doesn't
        while high - low > 1:
            mid = (low + high) // 2
            x = program[:mid]
            if self.program_fails(x):
                high = mid
            else:
                low = mid
        return program[:high]

    def find_failing_program(
        self,
    ):
        examples_found = 0
        best_example = None

        for _ in range(self.n_iters):
            program = self.generate_program()
            if self.program_fails(program):
                program = self.find_failing_initial_segment(program)
                examples_found += 1
                if (
                    (best_example is None) or
                    (len(program) < len(best_example))
                ):
                    best_example = program
                if examples_found >= self.good_enough:
                    return best_example

        if best_example is None:
            raise NoFailingProgram(
                ("Unable to find a failing program of length <= %d"
                 " after %d iterations") % (self.prog_length, self.n_iters)
            )
        return best_example

    def run_program(self, program):
        context = RunContext()
        context.run_program(program)
        return context

    def prune_program(self, program):
        context = RunContext(simulation=True)
        results = []
        for operation in program:
            if not operation.applicable(context.heights()):
                continue
            results.append(operation)
            try:
                context.execute(operation)
            except Exception:
                break

        return results

    def shrink(self, program):
        for i in xrange(len(program)):
            copy = list(program)
            del copy[i]
            yield self.prune_program(copy)
            if i < len(copy):
                del copy[i]
                yield self.prune_program(copy)

    def minimize_failing_program(self, program):
        assert self.program_fails(program)
        current_best = program
        while True:
            for child in self.shrink(current_best):
                if self.program_fails(child):
                    current_best = child
                    break
            else:
                return current_best
