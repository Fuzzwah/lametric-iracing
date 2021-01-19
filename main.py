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
from pprint import pprint
import logging, logging.handlers
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
    QSettings,
    pyqtSlot,
    pyqtSignal
)

import irsdk
import requests


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
        

class Widget(QWidget):
    def __init__(self):
        super().__init__()
 
        self.settings = QSettings(os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.ini"), QSettings.IniFormat)
        print(self.settings.fileName())
        try:
            self.lametric_ip(self.settings.value('lametric_ip'))
            self.lametric_api_key(self.settings.value('lametric_api_key'))
        except:
            pass
 
    def closeEvent(self, event):
        self.settings.setValue('lametric_ip', self.lametric_ip())
        self.settings.setValue('lametric_api_key', self.lametric_api_key())


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        if self.args.ipaddress:
            self.lametric_ip = self.args.ipaddress
        if self.args.key:
            self.lametric_api_key = self.args.key
        self.lametric_url = f"http://{self.lametric_ip}:8080/api/v2/device/notifications"

        self.driver = None

        self.setWindowTitle("LaMetric iRacing Data Sender")

        layout = QGridLayout()
        layout.setColumnMinimumWidth(1, 70)
        layout.setSpacing(10)

        iratingLabel = QLabel('iRating')
        iratingLabel.setFont(set_font(bold=True))
        layout.addWidget(iratingLabel, 1, 0, 1, 1)

        self.iratingField = QLineEdit()
        self.iratingField.setReadOnly(True)
        self.iratingField.setText("")
        self.iratingField.setFont(set_font())
        layout.addWidget(self.iratingField, 1, 1, 1, 3)

        licenseLabel = QLabel('License')
        licenseLabel.setFont(set_font(bold=True))
        layout.addWidget(licenseLabel, 2, 0, 1, 1)

        self.licenseField = QLineEdit()
        self.licenseField.setReadOnly(True)
        self.licenseField.setText("")
        self.licenseField.setFont(set_font())
        layout.addWidget(self.licenseField, 2, 1, 1, 3)

        bestLapLabel = QLabel('Best Lap')
        bestLapLabel.setFont(set_font(bold=True))
        layout.addWidget(bestLapLabel, 3, 0, 1, 1)

        self.bestLapField = QLineEdit()
        self.bestLapField.setReadOnly(True)
        self.bestLapField.setText("")
        self.bestLapField.setFont(set_font())
        layout.addWidget(self.bestLapField, 3, 1, 1, 3)

        self.debugBtn = QPushButton('Debug')
        self.debugBtn.clicked.connect(self.debug)
        layout.addWidget(self.saveBtn, 4, 1, 1, 1)

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

        self.timerBestLap = QTimer()
        self.timerBestLap.setInterval(1)
        self.timerBestLap.timeout.connect(self.best_lap)

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

    def data_collection_cycle(self):
        data = {
            "IRating": f"{self.driver['IRating']:,}",
            "LicString": self.driver['LicString'],
            "LapBestLapTime": self.driver['LapBestLapTime']
        }
        return data

    def update(self, data):
        if self.iratingField.text is not f"{data['IRating']}":
            self.iratingField.setText(f"{data['IRating']}")
        if self.licenseField.text is not f"{data['LicString']}":
            self.licenseField.setText(f"{data['LicString']}")
        if self.bestLapField.text is not f"{data['LapBestLapTime']}":
            self.bestLapField.setText(f"{data['LapBestLapTime']}")

        data = {
            "model": {
                    "frames": [{
                        "icon": "i43085",
                        "text": data['IRating']
                    }]
                }
            }

        if self.lametric_ip and self.lametric_api_key:
            self.send_notification(data)

    def best_lap(self):
        bestlap_worker = Worker(self.data_collection_cycle)
        bestlap_worker.signals.result.connect(self.update)
        
        self.threadpool.start(bestlap_worker)

    def onConnection(self):
        self.ir_connected = True
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(0,150,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage(('STATUS: iRacing client detected.'))

        for dvr in self.ir['DriverInfo']['Drivers']:
            if dvr['CarIdx'] == self.ir['DriverInfo']['DriverCarIdx']:
                self.driver = dvr
                break

    def onDisconnection(self):
        self.ir_connected = False
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')

    def send_notification(self, data):
            pprint(data)

            headers = {"Content-Type": "application/json; charset=utf-8"}
            basicAuthCredentials = ("dev", self.lametric_api_key)
            try:
                response = requests.post(
                    self.lametric_url,
                    headers=headers,
                    auth=basicAuthCredentials,
                    json=data,
                    timeout=1,
                )
                if self.args.debug:
                    pprint(response)
            except requests.exceptions.RequestException as err:
                print("Oops: Something Else: ", err)
            except requests.exceptions.ConnectionRefusedError as err:
                print("Connection Refused: ", err)
            except requests.exceptions.HTTPError as errh:
                print("Http Error: ", errh)
            except requests.exceptions.ConnectionError as errc:
                print("Error Connecting: ", errc)
            except requests.exceptions.Timeout as errt:
                print("Timeout: ", errt)

    def debug(self):
        pprint(self.driver)

def setup_logging():
    """ Everything required when the application is first initialized
    """

    basepath = os.path.abspath(".")

    # set up all the logging stuff
    LOG_FILENAME = os.path.join(basepath, "lametric.log")

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
    # setup logging
    setup_logging()

    # connect to the logger we set up
    log = logging.getLogger(__name__)
    app = QApplication([])
    window = MainWindow()
    sys.exit(app.exec_())
