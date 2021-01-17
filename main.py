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
import logging
import wave
import traceback

from PyQt5.QtGui import (
    QFont
)
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QTextEdit,
    QPushButton,
    QLineEdit,
    QGridLayout,
    QStatusBar
)
from PyQt5.QtCore import (
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    pyqtSlot,
    pyqtSignal
)


import irsdk
import configobj

def set_font(size=14, bold=False):
    font = QFont()
    font.setBold(bold)
    font.setPixelSize(size)
    return font


class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data
    
    error
        `tuple` (exctype, value, traceback.format_exc() )
    
    result
        `object` data returned from processing, anything

    progress
        `int` indicating % progress 

    '''
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    #progress = pyqtSignal(int)


class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and 
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()    

        # Add the callback to our kwargs
        #self.kwargs['progress_callback'] = self.signals.progress        

    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        
        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done
        

class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
    
        self.counter = 0

        self.setWindowTitle("LaMetric iRacing Data Sender")

        iratingLabel = QLabel('iRating')
        iratingLabel.setFont(set_font(bold=True))

        self.iratingField = QLineEdit()
        self.iratingField.setReadOnly(True)
        self.iratingField.setText("")
        self.iratingField.setFont(set_font())

        layout = QGridLayout()
        layout.setColumnMinimumWidth(1, 70)

        layout.setSpacing(10)

        layout.addWidget(iratingLabel, 1, 0, 1, 1)
        layout.addWidget(self.iratingField, 1, 1, 1, 3)

        w = QWidget()
        w.setLayout(layout)
    
        self.setCentralWidget(w)
    
        self.show()

        sb = QStatusBar()
        sb.setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        sb.setFixedHeight(20)
        self.setStatusBar(sb)
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')

        self.ir = irsdk.IRSDK()

        self.ir_connected = False
        self.car_in_world = False

        self.threadpool = QThreadPool()

        self.timerConnectionMonitor = QTimer()
        self.timerConnectionMonitor.setInterval(1000)
        self.timerConnectionMonitor.timeout.connect(self.irsdkConnectionMonitor)
        self.timerConnectionMonitor.start()


    def connection_check(self):
        if self.ir.is_connected:
            return True
        else:
            self.ir.startup(silent=True)
            try:
                if self.ir.is_connected:
                    return True
                else:            
                    return False
            except AttributeError:
                return False
             
    def connection_controller(self, now_connected):
        if now_connected and not self.ir_connected:
            self.onConnection()
        elif not now_connected and self.ir_connected:
            self.onDisconnection()
 
    def irsdkConnectionMonitor(self):
        monitor_worker = Worker(self.connection_check)
        monitor_worker.signals.result.connect(self.connection_controller)
        
        self.threadpool.start(monitor_worker)


    def onConnection(self):
        self.ir_connected = True
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(0,150,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage(('STATUS: iRacing client detected.'))

        for driver in self.ir['DriverInfo']['Drivers']:
            if driver['CarIdx'] == self.ir['DriverInfo']['DriverCarIdx']:
                car = driver['CarPath'].lower()
                car_full = driver['CarScreenName']
                break
        print(self.ir)
        self.iratingField.setText(self.ir['WeekendInfo']['TrackName'])

    def onDisconnection(self):
        self.ir_connected = False
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')

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
        config.write()

    # try to read in the config
    try:
        config = configobj.ConfigObj(args.configfile)

    except (IOError, KeyError, AttributeError) as e:
        print("Unable to successfully read config file: %s" % args.configfile)
        sys.exit(0)
    
    app = QApplication([])
    window = MainWindow()
    sys.exit(app.exec_())
