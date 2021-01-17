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

__program__ = "lametic-iracing"
__author__ = "Robert Crouch (rob.crouch@gmail.com)"
__copyright__ = "Copyright (C) 2021- Robert Crouch"
__license__ = "AGPL 3.0"
__version__ = "v0.210117"

import os
import sys
import time
import argparse
import logging, logging.handlers

import configobj
from PyQt5.QtCore import (
    QThread,
    QObject,
    pyqtSignal,
    pyqtSlot
)
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QFont

def set_font(size=14, bold=False):
    font = QFont()
    font.setBold(bold)
    font.setPixelSize(size)
    return font


class Worker(QObject):
    status = pyqtSignal()

    def __init__(self):
        super(Worker, self).__init__()
        self.var = "things"

    @pyqtSlot()
    def run(self):
        print("worker processing")
        time.sleep(2)


class App(QMainWindow):

    def __init__(self, parent=None):
        super(App, self).__init__(parent)

        self.version = "{}: {}".format(__program__, __version__)
        if args.debug:
            print(self.version)

        self.setStatusBarState("info", "Waiting")
        self.widgets = Widgets(self)
        self.setCentralWidget(self.widgets)

        self.setGeometry(300, 300, 400, 450)
        self.setWindowTitle('python-skeleton-qt5')
        self.show()

    def setStatusBarState(self, state, msg):
        if state == "info":
            bgcolour = "rgba(0,0,100,200)"
        elif state == "error":
            bgcolour = "rgba(150,0,0,200)"
        elif state == "success":
            bgcolour = "rgba(0,150,0,200)"
        else:
            bgcolour = "rgba(50,50,50,200)"

        sb = QStatusBar()
        sb.setStyleSheet("QStatusBar{{padding-left:8px;padding-bottom:2px;background:{};color:white;font-weight:bold;}}".format(bgcolour))
        sb.setFixedHeight(20)
        self.setStatusBar(sb)
        self.statusBar().showMessage("STATUS: {}".format(msg))


class Widgets(QWidget):

    def __init__(self, parent):
        QWidget.__init__(self, parent)

        self.statusBar = parent.statusBar

        self.initUI()

    def startWorker(self):
        self.worker = Worker()
        self.thread_worker = QThread()

        self.worker.status.connect(self.onStatusChange)
        self.worker.moveToThread(self.thread_worker)
        self.thread_worker.started.connect(self.worker.run)
        self.thread_worker.start()

    def initUI(self):
        label = QLabel('lorem')
        label.setFont(set_font(bold=True))

        self.field = QLineEdit()
        self.field.setReadOnly(True)
        self.field.setText("")
        self.field.setFont(set_font())
        self.saveBtn = QPushButton('Save', self)
        self.saveBtn.clicked.connect(self.save)
        self.cancelBtn = QPushButton('Cancel', self)
        self.cancelBtn.clicked.connect(self.cancel)

        grid = QGridLayout()
        grid.setColumnMinimumWidth(1, 70)

        grid.setSpacing(10)

        grid.addWidget(label, 1, 0, 1, 1)
        grid.addWidget(self.field, 1, 1, 1, 3)

        grid.addWidget(self.saveBtn, 2, 0, 1, 1)
        grid.addWidget(self.cancelBtn, 2, 1, 1, 1)

        self.setLayout(grid)

    def onStatusChange(self, i):
        app.setStatusBarState("info", "test")

    def save(self):
        app.setStatusBarState("success", "saved")

    def cancel(self):
        app.setStatusBarState("error", "cancelled")


def parse_args(argv):
    """ Read in any command line options and return them
    """

    # Define and parse command line arguments
    parser = argparse.ArgumentParser(description=__program__)
    parser.add_argument("--logfile", help="file to write log to", default="%s.log" % __program__)
    parser.add_argument("--configfile", help="use a different config file", default="config.ini")
    parser.add_argument("--newconfig", action='store_true', default=False)
    parser.add_argument("--debug", action='store_true', default=False)

    # uncomment this if you want to force at least one command line option
    # if len(sys.argv)==1:
    #   parser.print_help()
    #   sys.exit(1)

    args = parser.parse_args()

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
        LOG_LEVEL = logging.INFO  # Could be e.g. "DEBUG" or "WARNING"

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


if __name__ == '__main__':
    # call function to parse command line arguments
    args = parse_args(sys.argv)

    # setup logging
    setup_logging(args)

    # connect to the logger we set up
    log = logging.getLogger(__name__)

    if not os.path.isfile(args.configfile) or args.newconfig:
        config = configobj.ConfigObj()
        config.filename = args.configfile

        config['Options'] = {}
        config['Options']['things'] = 'stuff'
        config.write()

    # try to read in the config
    try:
        config = configobj.ConfigObj(args.configfile)

    except (IOError, KeyError, AttributeError) as e:
        print("Unable to successfully read config file: %s" % args.configfile)
        sys.exit(0)

    qapp = QApplication(sys.argv)
    app = App()

    sys.exit(qapp.exec_())