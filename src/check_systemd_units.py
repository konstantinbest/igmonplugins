#!/usr/bin/env python
"""InnoGames Monitoring Plugins - Systemd Units Check

This is a Nagios script to check all or some units of "systemd".
It checks for anomalies of those units like the ones not anymore
defined but still running, and them being dead.  Normally returns
at most warning, if no critical units are specified.

It returns:

* Critical when a critical unit is failed
* Warning when a critical unit is not running
* Warning when a non-critical unit is failed
* Warning for other anomalies

Copyright (c) 2018 InnoGames GmbH
"""
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the 'Software'), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from argparse import ArgumentParser
from subprocess import CalledProcessError, check_output
from sys import exit


class Problem:
    """Enum for problems that can apply to the units"""

    # From more important to less
    failed = 0
    activating_auto_restart = 1
    not_loaded_but_not_inactive = 2
    not_loaded_but_not_dead = 3
    dead = 4
    not_loaded = 5


def parse_args():
    """Parse the arguments

    We are returning them as a dict for callers convenience.
    """
    parser = ArgumentParser()
    parser.add_argument(
        '-a',
        action='store_true',
        dest='check_all',
        default=False,
        help='check all units (it is the default when no services are passed)',
    )
    parser.add_argument(
        '-s',
        action='append',
        dest='critical_units',
        default=[],
        help='unit to return critical when failed',
    )
    parser.add_argument(
        '-i',
        action='append',
        dest='ignored_units',
        default=[],
        help='unit to ignore',
    )

    return parser.parse_args()


def main():
    """The main program"""
    args = parse_args()
    command = 'systemctl --all --no-legend --no-pager list-units'
    if not args.check_all:
        for unit in args.critical_units:
            command += ' ' + unit
    try:
        output = check_output(command.split()).decode()
    except CalledProcessError as error:
        print('UNKNOWN: ' + str(error))
        exit_code = 3
    else:
        criticals, warnings = process(output, args)
        if criticals:
            print('CRITICAL: ' + get_message(criticals + warnings))
            exit_code = 2
        elif warnings:
            print('WARNING: ' + get_message(warnings))
            exit_code = 1
        else:
            print('OK')
            exit_code = 0

    exit(exit_code)


def process(output, args):
    criticals = []
    warnings = []

    for line in output.splitlines():
        unit_split = line.strip().split(None, 4)
        unit_name = unit_split[0]

        problem = check_unit(*unit_split[0:4])
        if problem is None:
            continue

        is_critical = any(
            match_unit(p, unit_name) for p in args.critical_units
        )
        if not is_critical and problem >= Problem.dead:
            continue

        if is_critical and problem < Problem.dead:
            criticals.append((problem, unit_name))
        else:
            warnings.append((problem, unit_name))

    return criticals, warnings


def match_unit(pattern, unit):
    if pattern.endswith('@*') and '@' in unit:
        return pattern[:-len('@*')] == unit.split('@', 1)[0]
    return pattern == unit


def check_unit(unit_name, serv_load, serv_active, serv_sub):
    """Detect problems of a unit"""
    if serv_load != 'loaded':
        if serv_active != 'inactive':
            return Problem.not_loaded_but_not_inactive

        if serv_sub != 'dead':
            return Problem.not_loaded_but_not_dead

        return Problem.not_loaded

    if serv_active == 'failed':
        return Problem.failed

    if serv_sub == 'auto-restart':
        if get_exit_code(unit_name) != 0:
            return Problem.activating_auto_restart
    elif serv_sub == 'dead':
        return Problem.dead
    elif serv_sub == 'failed':
        return Problem.failed


def get_exit_code(unit_name):
    command = 'systemctl show -p ExecMainStatus {}'.format(unit_name)
    try:
        output = check_output(command.split())
    except CalledProcessError:
        return -1
    return int(output[len('ExecMainStatus='):])


def get_message(problems):
    """Format the message to print out"""
    problem_names = {
        v: k.replace('_', ' ')
        for k, v in vars(Problem).items()
        if isinstance(v, int)
    }
    message = ''
    last_problem = None
    for problem, unit in problems:
        if problem != last_problem:
            message += problem_names[problem] + ': '
            last_problem = problem
        message += unit + ' '

    return message


if __name__ == '__main__':
    main()
