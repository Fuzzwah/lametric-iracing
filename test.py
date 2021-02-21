#!/usr/bin/env python
# -*- coding: utf-8 -*-

#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License along
#   with this program; if not, write to the Free Software Foundation, Inc.,
#   51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
SYNOPSIS

    python main.py [-h,--help] [-l,--log] [--debug]

DESCRIPTION

    TODO This describes how to use this script. This docstring
    will be printed by the script if there is an error or
    if the user requests help (-h or --help).

EXAMPLES

    TODO: Show some examples of how to use this script.

AUTHOR

    Robert Crouch (rob.crouch@gmail.com)

VERSION

    $Id$
"""

__program__ = "lametric_tester"
__author__ = "Robert Crouch (rob.crouch@gmail.com)"
__copyright__ = "Copyright (C) 2021- Robert Crouch"
__license__ = "LGPL 3.0"
__version__ = "v0.210221"

import os
import sys
import argparse
import logging, logging.handlers
import json
from time import sleep
from random import choice

import requests
from urllib3.exceptions import NewConnectionError, ConnectTimeoutError, MaxRetryError

class App(object):
    """ The main class of your application
    """

    def __init__(self, log, args):
        self.log = log
        self.args = args
        self.version = "{}: {}".format(__program__, __version__)

        self.log.info(self.version)
        if self.args.debug:
            print(self.version)

        self.previous_notification = None

        print(self.queued_nofitications())

        self.send_ratings()
        sleep(3)
        self.send_random_flag()
        sleep(3)
        self.send_random_flag()
        sleep(3)
        self.send_random_flag()

    flags = {
        'start_hidden': 'a43445',
        'checkered': 'a43490',
        'white': 'a43444',
        'green': 'a43445',
        'yellow': 'a43439',
        'yellow_waving': 'a43439',
        'red': 'a43491',
        'blue': 'a43495',
        'debris': 'a43497',
        'green_held': 'i43445',
        'random_waving': 'a43458',
        'caution': 'i43439',
        'caution_waving': 'a43439',
        'black': 'a43499',
        'disqualify': 'a43492',
        'furled': 'a43496',
        'repair': 'a43500',        
    }

    def send_random_flag(self):
        flag = choice(list(self.flags.keys()))
        icon = self.flags[flag]

        data = {
            "priority": "critical",
            "icon_type":"none",
            "model": {
                "cycles": 2,
                "frames": [
                    {"icon": f"{icon}", "text": f"{flag}"}
                ]
            }
        }

        self.send_notification(data)

    def send_ratings(self):
        data = {
            "priority": "critical",
            "icon_type":"none",
            "model": {
                "cycles": 0,
                "frames": [
                    {"icon": 'i43085', "text": '5,429'},
                    {"icon": 'i43595', "text": 'A 4.11'}
                ]
            }
        }

        self.send_notification(data)

    def send_notification(self, data):

        if self.previous_notification:
            self.dismiss_nofitication(self.previous_notification)
            sleep(0.2)

        lametric_url = f"http://{self.args.ip}:8080/api/v2/device/notifications"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        basicAuthCredentials = ("dev", self.args.key)

        response = None
        try:
            response = requests.post(
                lametric_url,
                headers=headers,
                auth=basicAuthCredentials,
                json=data,
                timeout=1,
            )
        except (NewConnectionError, ConnectTimeoutError, MaxRetryError) as err:
            print("Failed to send data to LaMetric device: ", err)
        except requests.exceptions.RequestException as err:
            print("Oops: Something Else: ", err)
        except requests.exceptions.HTTPError as errh:
            print("Http Error: ", errh)
        except requests.exceptions.ConnectionError as errc:
            print("Error Connecting: ", errc)
        except requests.exceptions.Timeout as errt:
            print("Timeout: ", errt)

        try:
            self.previous_notification = response['success']['id']
            return True
        except:
            return False

    def dismiss_nofitication(self, notification_id):

        lametric_url = f"http://{self.args.ip}:8080/api/v2/device/notifications/{notification_id}"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        basicAuthCredentials = ("dev", self.args.key)

        response = None
        try:
            response = requests.delete(
                lametric_url,
                headers=headers,
                auth=basicAuthCredentials,
                timeout=1,
            )
        except (NewConnectionError, ConnectTimeoutError, MaxRetryError) as err:
            print("Failed to send data to LaMetric device: ", err)
        except requests.exceptions.RequestException as err:
            print("Oops: Something Else: ", err)
        except requests.exceptions.HTTPError as errh:
            print("Http Error: ", errh)
        except requests.exceptions.ConnectionError as errc:
            print("Error Connecting: ", errc)
        except requests.exceptions.Timeout as errt:
            print("Timeout: ", errt)

        if response:
            return json.loads(response.text)
        else:
            return False


    def queued_nofitications(self):

        lametric_url = f"http://{self.args.ip}:8080/api/v2/device/notifications"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        basicAuthCredentials = ("dev", self.args.key)

        response = None
        try:
            response = requests.get(
                lametric_url,
                headers=headers,
                auth=basicAuthCredentials,
                timeout=1,
            )
        except (NewConnectionError, ConnectTimeoutError, MaxRetryError) as err:
            print("Failed to send data to LaMetric device: ", err)
        except requests.exceptions.RequestException as err:
            print("Oops: Something Else: ", err)
        except requests.exceptions.HTTPError as errh:
            print("Http Error: ", errh)
        except requests.exceptions.ConnectionError as errc:
            print("Error Connecting: ", errc)
        except requests.exceptions.Timeout as errt:
            print("Timeout: ", errt)

        if response:
            return json.loads(response.text)
        else:
            return False



def parse_args(argv):
    """ Read in any command line options and return them
    """

    # Define and parse command line arguments
    parser = argparse.ArgumentParser(description=__program__)
    parser.add_argument("--logfile", help="file to write log to", default="%s.log" % __program__)
    parser.add_argument("--debug", action='store_true', default=False)
    parser.add_argument("--ip", help="LaMetric Time device's IP address", default=None)
    parser.add_argument("--key", help="LaMetric Time device's API key", default=None)

    args = parser.parse_args()

    if not args.ip or not args.key:
       parser.print_help()
       sys.exit(1)


    return args

def setup_logging(args):
    """ Everything required when the application is first initialized
    """

    basepath = os.path.abspath(".")

    # set up all the logging stuff
    LOG_FILENAME = os.path.join(basepath, "%s" % args.logfile)

    if args.debug:
        LOG_LEVEL = logging.DEBUG
    else:
        LOG_LEVEL = logging.WARNING  # Could be e.g. "DEBUG" or "WARNING"

    # Configure logging to log to a file, making a new file at midnight and keeping the last 3 day's data
    # Give the logger a unique name (good practice)
    log = logging.getLogger(__name__)
    # Set the log level to LOG_LEVEL
    log.setLevel(LOG_LEVEL)
    # Make a handler that writes to a file, making a new file at midnight and keeping 3 backups
    handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="midnight", backupCount=3)
    # Format each log message like this
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
    # Attach the formatter to the handler
    handler.setFormatter(formatter)
    # Attach the handler to the logger
    log.addHandler(handler)

def main(raw_args):
    """ Main entry point for the script.
    """

    # call function to parse command line arguments
    args = parse_args(raw_args)

    # setup logging
    setup_logging(args)

    # connect to the logger we set up
    log = logging.getLogger(__name__)

    # fire up our base class and get this app cranking!
    app = App(log, args)

    # things that the app does go here:


    pass

if __name__ == '__main__':
    sys.exit(main(sys.argv))



