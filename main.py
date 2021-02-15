#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pprint import pprint
from dataclasses import dataclass, field
from datetime import timedelta
from time import sleep
from random import random
import traceback
import requests
from urllib3.exceptions import NewConnectionError, ConnectTimeoutError, MaxRetryError
from typing import Optional
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import (
    QCoreApplication,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    QSettings,
    pyqtSlot,
    pyqtSignal
)
from window import Window, Dialog
from pyirsdk import (
    IRSDK,
    Flags
)

def ordinal(num):
    """
    Take number and return the ordinal st, nd, th.
    :num: int
    :return: str
    """
    num_str = str(num)

    SUFFIXES = {1: 'st', 2: 'nd', 3: 'rd'}
    # Check for 11-14 because those are abnormal
    if int(num_str[-2:]) > 10 and int(num_str[-2:]) < 14:
        return "{:,}th".format(num)
    else:
        suffix = SUFFIXES.get(int(num_str[-1:]), 'th')
    return "{:,}{}".format(num, suffix)


@dataclass
class Driver(object):
    """ a generic object to collect up the information about the driver
    """

    caridx: int = None
    name: str = None
    irating: int = None
    license_string: str = None
    license_letter: str = None
    safety_rating: float = None


@dataclass
class Data(object):
    """ a generic object to collect up the data we need from the irsdk
    """

    position: int = None
    cars_in_class: int = None
    laps: int = None
    laps_left: int = None
    laps_total: int = None
    last_laptime: str = None
    best_laptime: str = None
    fuel_per_lap: float = None
    fuel_left: float = None
    time_left: float = None
    track_temp: float = None
    flags: int = None


@dataclass
class Icons(object):
    """ a generic object to pass around information regarding the icons
    """

    ir: str = 'i43085'

    # flags
    start_hidden: str = 'a43445'
    checkered: str = 'a43490'
    white: str = 'a43444'
    green: str = 'a43445'
    yellow: str = 'a43439'
    yellow_waving: str = 'a43439'
    red: str = 'a43491'
    blue: str = 'a43495'
    debris: str = 'a43497'
    green_held: str = 'i43445'
    random_waving: str = 'a43458'
    caution: str = 'i43439'
    caution_waving: str = 'a43439'
    black: str = 'a43499'
    disqualify: str = 'a43492'
    furled: str = 'a43496'
    repair: str = 'a43500'
    # we don't have icons for these yet
    crossed: str = ir
    one_lap_to_green: str = ir
    ten_to_go: str = ir
    five_to_go: str = ir

    # license icons
    license_letter_r: str = 'i43591'
    license_letter_d: str = 'i43592'
    license_letter_c: str = 'i43593'
    license_letter_b: str = 'i43594'
    license_letter_a: str = 'i43595'
    license_letter_p: str = 'i43596'

    # purple for fastest lap
    purple: str = '43599'

    laps: str = '43645'
    gain_position: str = 'a43651'
    lose_position: str = 'a43652'    


@dataclass
class State(object):
    """ a generic object to pass around information regarding the current state
    """

    ir_connected: bool = False
    car_in_world: bool = False
    last_car_setup_tick: int = -1
    start_hidden_sent: bool = False
    previous_event_sent: str = None


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


class MainWindow(Window):
    def __init__(self):
        super().__init__("ui/MainWindow.ui")

        self.dialog: Optional[SettingsDialog] = None

        mnu = self.actionSettings
        mnu.setShortcut("Ctrl+O")
        mnu.setStatusTip("Show settings")
        mnu.triggered.connect(self.show_settings)

        sb = self.statusBar()
        sb.setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        sb.setFixedHeight(20)
        self.setStatusBar(sb)
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')

        self.register_widget(self.checkBox_IRating, default=True)
        self.register_widget(self.checkBox_License, default=True)
        self.register_widget(self.checkBox_Position, default=True)
        self.register_widget(self.checkBox_Laps, default=True)
        self.register_widget(self.checkBox_LapsLeft, default=True)
        self.register_widget(self.lineEdit_Name)
        self.register_widget(self.lineEdit_IRating)
        self.register_widget(self.lineEdit_License)

        self.register_widget(self.checkBox_LastLap, default=True)
        self.register_widget(self.checkBox_BestLap, default=True)
        self.register_widget(self.checkBox_FuelPerLap, default=True)
        self.register_widget(self.checkBox_FuelLeft, default=True)
        self.register_widget(self.checkBox_TimeLeft, default=True)
        self.register_widget(self.checkBox_Flags, default=True)

        self.ir = IRSDK()
        self.state = State()
        self.sent_data = Data()
        self.data = Data()

        self.threadpool = QThreadPool()

        self.timerConnectionMonitor = QTimer()
        self.timerConnectionMonitor.setInterval(10000)
        self.timerConnectionMonitor.timeout.connect(self.irsdkConnectionMonitor)

        self.get_queue()

        """
        ('[ { "created" : "2021-02-15T22:18:32Z", "expiration_date" : '
        '"2021-02-15T22:20:32Z", "id" : "3275", "model" : { "cycles" : 0, "frames" : '
        '[ { "icon" : "i43085", "text" : "1 to Green" } ] }, "priority" : "warning", '
        '"type" : "external" }, { "created" : "2021-02-15T22:25:18Z", '
        '"expiration_date" : "2021-02-15T22:27:18Z", "id" : "3323", "model" : { '
        '"cycles" : 0, "frames" : [ { "icon" : "i43085", "text" : "1 to Green" } ] }, '
        '"priority" : "warning", "type" : "external" }, { "created" : '
        '"2021-02-15T22:24:27Z", "expiration_date" : "2021-02-15T22:26:27Z", "id" : '
        '"3321", "model" : { "cycles" : 0, "frames" : [ { "icon" : "i43085", "text" : '
        '"1" }, { "icon" : "i43591", "text" : "0.01" } ] }, "priority" : "info", '
        '"type" : "external" }, { "created" : "2021-02-15T22:25:18Z", '
        '"expiration_date" : "2021-02-15T22:27:18Z", "id" : "3322", "model" : { '
        '"cycles" : 0, "frames" : [ { "icon" : "a43445", "text" : "Start" } ] }, '
        '"priority" : "info", "type" : "external" }, { "created" : '
        '"2021-02-15T22:25:18Z", "expiration_date" : "2021-02-15T22:27:18Z", "id" : '
        '"3324", "model" : { "cycles" : 0, "frames" : [ { "icon" : "43599", "text" : '
        '"0:0.000" } ] }, "priority" : "info", "type" : "external" }, { "created" : '
        '"2021-02-15T22:25:18Z", "expiration_date" : "2021-02-15T22:27:18Z", "id" : '
        '"3325", "model" : { "cycles" : 0, "frames" : [ { "icon" : "a43651", "text" : '
        '"0th / 64" } ] }, "priority" : "info", "type" : "external" }, { "created" : '
        '"2021-02-15T22:25:18Z", "expiration_date" : "2021-02-15T22:27:18Z", "id" : '
        '"3326", "model" : { "cycles" : 0, "frames" : [ { "icon" : "43645", "text" : '
        '"-1 / \\u221e" } ] }, "priority" : "info", "type" : "external" }, { '
        '"created" : "2021-02-15T22:25:18Z", "expiration_date" : '
        '"2021-02-15T22:27:18Z", "id" : "3327", "model" : { "cycles" : 0, "frames" : '
        '[ { "icon" : "i43085", "text" : "1" }, { "icon" : "i43591", "text" : "0.01" '
        '} ] }, "priority" : "info", "type" : "external" } ]')
        """        


        self.timerMainCycle = QTimer()
        self.timerMainCycle.setInterval(50000)
        self.timerMainCycle.timeout.connect(self.main_cycle)

        if self.irsdk_connection_check():
            self.irsdk_connection_controller(True)
        
        self.timerConnectionMonitor.start()

        s = QSettings()
        #s.clear()
        #pprint(s.allKeys())

    # here we check if we are connected to iracing
    # so we can retrieve some data
    def irsdk_connection_check(self):
        if self.state.ir_connected and not (self.ir.is_initialized and self.ir.is_connected):
            return False
        elif not self.state.ir_connected and self.ir.startup(silent=True) and self.ir.is_initialized and self.ir.is_connected:
            return True
        elif self.ir.is_initialized and self.ir.is_connected:
            return True
             
    def irsdk_connection_controller(self, now_connected):
        if now_connected and not self.state.ir_connected:
            self.onConnection()
        elif not now_connected and self.state.ir_connected:
            self.onDisconnection()
 
    def irsdkConnectionMonitor(self):
        monitor_worker = Worker(self.irsdk_connection_check)
        monitor_worker.signals.result.connect(self.irsdk_connection_controller)
        
        self.threadpool.start(monitor_worker)

    def update_data(self, attr, value):
        try:
            setattr(self.data, attr, value)
        except KeyError:
            setattr(self.data, attr, None)

    def data_collection_cycle(self):
        self.ir.freeze_var_buffer_latest()
        self.update_data('position', int(self.ir['PlayerCarClassPosition']))
        self.update_data('cars_in_class', int(len(self.ir['CarIdxClassPosition'])))
        try:
            minutes, seconds = divmod(float(self.ir['LapBestLapTime']), 60)
            bestlaptime = f"{minutes:.0f}:{seconds:.3f}"
        except:
            bestlaptime = ""
        self.update_data('best_laptime', bestlaptime)
        try:
            minutes, seconds = divmod(float(self.ir['LapLastLapTime']), 60)
            lastlaptime = f"{minutes:.0f}:{seconds:.3f}"
        except:
            lastlaptime = ""
        try:
            time_left = timedelta(seconds=int(self.ir['SessionTimeRemain']))
        except:
            time_left = ""
        self.update_data('last_laptime', lastlaptime)
        self.update_data('fuel_left', self.ir['FuelLevel'])
        self.update_data('laps', int(self.ir['LapCompleted']))
        self.update_data('laps_left', int(self.ir['SessionLapsRemainEx']))
        self.update_data('laps_total', int(self.ir['LapCompleted']) + int(self.ir['SessionLapsRemainEx']))
        self.update_data('time_left', str(time_left))
        self.update_data('flags', int(self.ir['SessionFlags']))
        self.ir.unfreeze_var_buffer_latest()

    def process_data(self):

        if self.lineEdit_BestLap.text() != self.data.best_laptime:
            self.lineEdit_BestLap.setText(self.data.best_laptime)

        if self.lineEdit_Position.text() != f"{ordinal(self.data.position)} / {self.data.cars_in_class}":
            self.lineEdit_Position.setText(f"{ordinal(self.data.position)} / {self.data.cars_in_class}")
            
        if self.lineEdit_LastLap.text() != self.data.last_laptime:
            self.lineEdit_LastLap.setText(self.data.last_laptime)

        if self.lineEdit_Laps.text() != f"{self.data.laps}":
            self.lineEdit_Laps.setText(f"{self.data.laps}")

        if self.lineEdit_TimeLeft.text() != f"{self.data.time_left}":
            self.lineEdit_TimeLeft.setText(f"{self.data.time_left}")

        if self.lineEdit_FuelLeft.text() != f"{self.data.fuel_left:.2f} L":
            self.lineEdit_FuelLeft.setText(f"{self.data.fuel_left:.2f} L")

        if self.lineEdit_LapsLeft.text() != f"{self.data.laps_left}":
            if self.data.laps_left == 32767.0:
                self.data.laps_left = "∞"
            self.lineEdit_LapsLeft.setText(f"{self.data.laps_left}")        

        if self.data.flags & Flags.start_hidden and not self.state.start_hidden_sent:
            self.state.start_hidden_sent = True
            self.send_notification("start_hidden", "Start")

        if self.data.flags & Flags.checkered:
            self.send_notification("checkered", "Finish")

        if self.data.flags & Flags.white:
            self.send_notification("white", "White")

        if self.data.flags & Flags.green:
            self.send_notification("green", "Green")

        if self.data.flags & Flags.yellow:
            self.send_notification("yellow", "Yellow")

        if self.data.flags & Flags.red:
            self.send_notification("red", "Red")

        if self.data.flags & Flags.blue:
            self.send_notification("blue", "Blue")

        if self.data.flags & Flags.debris:
            self.send_notification("debris", "Debris")

        if self.data.flags & Flags.crossed:
            self.send_notification("crossed", "Crossed")

        if self.data.flags & Flags.yellow_waving:
            self.send_notification("yellow_waving", "Yellow")

        if self.data.flags & Flags.one_lap_to_green:
            self.send_notification("one_lap_to_green", "1 to Green")

        if self.data.flags & Flags.green_held:
            self.send_notification("green_held", "Green")

        if self.data.flags & Flags.ten_to_go:
            self.send_notification("ten_to_go", "10 to go")

        if self.data.flags & Flags.five_to_go:
            self.send_notification("five_to_go", "5 to go")

        if self.data.flags & Flags.random_waving:
            self.send_notification("random_waving", "Random")

        if self.data.flags & Flags.caution:
            self.send_notification("caution", "Caution")

        if self.data.flags & Flags.caution_waving:
            self.send_notification("caution_waving", "Caution")

        if self.data.flags & Flags.black:
            self.send_notification("black", "Black")

        if self.data.flags & Flags.disqualify:
            self.send_notification("disqualify", "DQ")

        if self.data.flags & Flags.furled:
            self.send_notification("furled", "Warning")

        if self.data.flags & Flags.repair:
            self.send_notification("repair", "Damage")

        if self.sent_data.best_laptime != self.data.best_laptime and self.checkBox_BestLap.isChecked():
            self.lineEdit_BestLap.setText(self.data.best_laptime)
            self.send_notification("purple", self.data.best_laptime)            

        if self.sent_data.position != self.data.position and self.checkBox_Position.isChecked():
            self.lineEdit_Position.setText(f"{ordinal(self.data.position)} / {self.data.cars_in_class}")
            event = "gain_position"
            if self.sent_data.position:
                if self.sent_data.position < self.data.position:
                    event = "lose_position"
            self.send_notification(event, f"{ordinal(self.data.position)} / {self.data.cars_in_class}")            

        if self.sent_data.laps != self.data.laps and self.checkBox_Laps.isChecked():
            self.lineEdit_Laps.setText(f"{self.data.laps}")
            if self.data.laps_total > 32000:
                laps_total = "∞"
            else:
                laps_total = self.data.laps_total
            self.lineEdit_LapsLeft.setText(f"{self.data.laps_left}")
            self.send_notification('laps', f"{self.data.laps} / {laps_total}")

        if self.state.previous_event_sent != "ratings":
            self.send_notification('ratings', None)


    def main_cycle(self):
        main_cycle_worker = Worker(self.data_collection_cycle)
        main_cycle_worker.signals.result.connect(self.process_data)
        
        self.threadpool.start(main_cycle_worker)

    def onConnection(self):
        try:
            self.timerConnectionMonitor.stop()
        except:
            pass
        self.state.ir_connected = True
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(0,150,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage(('STATUS: iRacing client detected.'))

        self.driver = Driver()

        for dvr in self.ir['DriverInfo']['Drivers']:
            if dvr['CarIdx'] == self.ir['DriverInfo']['DriverCarIdx']:
                self.driver.caridx = dvr['CarIdx']
                self.driver.name = dvr['UserName']
                self.driver.irating = int(dvr['IRating'])
                self.driver.license_string = dvr['LicString']
                license_letter, safety_rating = dvr['LicString'].split(' ')
                self.driver.license_letter = license_letter
                self.driver.safety_rating = float(safety_rating)

                self.send_notification("ratings", None)

                self.lineEdit_Name.setText(self.driver.name)
                self.lineEdit_IRating.setText(f"{self.driver.irating:,}")
                self.lineEdit_License.setText(self.driver.license_string)

                break

        self.timerMainCycle.start()

    def onDisconnection(self):
        self.state = State()
        self.ir.shutdown()

        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')
        self.timerMainCycle.stop()
        self.timerConnectionMonitor.start()

    def get_queue(self):
        s = QSettings()

        try:
            self.lametric_ip = s.value('lametric-iracing/Settings/laMetricTimeIPLineEdit')
        except:
            self.lametric_ip = None
        try:
            self.lametric_api_key = s.value('lametric-iracing/Settings/aPIKeyLineEdit')
        except:
            self.lametric_api_key = None

        if self.lametric_ip and self.lametric_api_key:
            lametric_url = f"http://{self.lametric_ip}:8080/api/v2/device/notifications"
            headers = {"Content-Type": "application/json; charset=utf-8"}
            basicAuthCredentials = ("dev", self.lametric_api_key)
            try:
                response = requests.get(
                    lametric_url,
                    headers=headers,
                    auth=basicAuthCredentials,
                    timeout=1,
                )
                pprint(response.text)
            except (NewConnectionError, ConnectTimeoutError, MaxRetryError) as err:
                print("Failed to send data to LaMetric device: ", err)
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
        

    def send_notification(self, event, text):
        s = QSettings()

        if event == "ratings":
            json = {
                "priority": "info",
                "icon_type":"none",
                "model": {
                    "cycles": 0,
                    "frames": []
                }
            }            
            if self.checkBox_IRating.isChecked():
                json["model"]["frames"].append({"icon": "i43085", "text": f"{self.driver.irating:,}"})

            if self.checkBox_License.isChecked():
                icon = Icons.ir
                if self.driver.license_letter == 'R':
                    icon = Icons.license_letter_r
                elif self.driver.license_letter == 'D':
                    icon = Icons.license_letter_d
                elif self.driver.license_letter == 'C':
                    icon = Icons.license_letter_c
                elif self.driver.license_letter == 'B':
                    icon = Icons.license_letter_b
                elif self.driver.license_letter == 'A':
                    icon = Icons.license_letter_a
                elif self.driver.license_letter == 'P':
                    icon = Icons.license_letter_p

                json["model"]["frames"].append({"icon": icon, "text": f"{self.driver.safety_rating}"})

        else:

            if event in ('checkered', 'white', 'green', 'yellow', 'red', 'blue', 'debris', 'crossed', 'yellow_waving', 'one_lap_to_green', 'green_held', 'ten_to_go', 'five_to_go', 'random_waving', 'caution', 'caution_waving', 'black', 'disqualify', 'furled', 'repair'):
                priority = "warning"
            else:
                priority = "info"

            icon = getattr(Icons, event)

            json = {
                "priority": priority,
                "icon_type": "none",
                "lifetime ": 1,
                "model": {
                    "cycles": 0,
                    "frames": [{"icon": icon, "text": text}]
                }
            }

        try:
            self.lametric_ip = s.value('lametric-iracing/Settings/laMetricTimeIPLineEdit')
        except:
            self.lametric_ip = None
        try:
            self.lametric_api_key = s.value('lametric-iracing/Settings/aPIKeyLineEdit')
        except:
            self.lametric_api_key = None

        if self.lametric_ip and self.lametric_api_key:
            lametric_url = f"http://{self.lametric_ip}:8080/api/v2/device/notifications"
            headers = {"Content-Type": "application/json; charset=utf-8"}
            basicAuthCredentials = ("dev", self.lametric_api_key)
            if len( json["model"]["frames"]) > 0 and event != self.state.previous_event_sent:
                print(event)
                self.state.previous_event_sent = event
                try:
                    response = requests.post(
                        lametric_url,
                        headers=headers,
                        auth=basicAuthCredentials,
                        json=json,
                        timeout=1,
                    )
                except (NewConnectionError, ConnectTimeoutError, MaxRetryError) as err:
                    print("Failed to send data to LaMetric device: ", err)
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

    def show_settings(self):
        self.open_dialog()

    @pyqtSlot()
    def on_settingsButton_clicked(self):
        self.open_dialog()

    @pyqtSlot()
    def on_settingsButtonModal_clicked(self):
        self.open_dialog(True)

    def open_dialog(self, modal: bool = False):
        if self.dialog is None:
            self.dialog = SettingsDialog()

        self.dialog.show(modal)

    @pyqtSlot()
    def on_testButton_clicked(self):
        count = 0
        position = 10
        bestlap = 1000
        self.driver = Driver()

        self.driver.caridx = 1
        self.driver.name = "Driver Name"
        self.driver.irating = 1350
        self.driver.license_string = "A 4.99"
        license_letter, safety_rating = "A 4.99".split(' ')
        self.driver.license_letter = license_letter
        self.driver.safety_rating = float(safety_rating)

        max = 10
        min_lap = 13

        while count < max + 1:
            lastlap = min_lap + (random() * 3)
            if lastlap < bestlap:
                bestlap = lastlap
            if count % 2 == 0:
                position = position - 1
            self.update_data('position', position)
            self.update_data('cars_in_class', 30)
            try:
                minutes, seconds = divmod(float(bestlap), 60)
                bestlaptime = f"{minutes:.0f}:{seconds:.3f}"
            except:
                bestlaptime = ""
            self.update_data('best_laptime', bestlaptime)
            try:
                minutes, seconds = divmod(float(lastlap), 60)
                lastlaptime = f"{minutes:.0f}:{seconds:.3f}"
            except:
                lastlaptime = ""
            try:
                time_left = timedelta(seconds=int(max - count))
            except:
                time_left = ""
            self.update_data('last_laptime', lastlaptime)
            self.update_data('laps', count)
            self.update_data('laps_left', max - count)
            self.update_data('fuel_left', 10.0)
            self.update_data('time_left', str(time_left))
            if count % 13 == 0:
                self.update_data('flags', 268763136)
            else:
                self.update_data('flags', 268697600)
            count += 1

            sleep(min_lap + 2)

            self.process_data()

    def closeEvent(self, e):
        super().closeEvent(e)
        self.ir.shutdown()
        self.timerConnectionMonitor.stop()
        self.timerMainCycle.stop()
        e.accept()
        QCoreApplication.exit()


class SettingsDialog(Dialog):
    def __init__(self):
        super(SettingsDialog, self).__init__("ui/SettingsDialog.ui")

        self.register_widget(self.laMetricTimeIPLineEdit)
        self.register_widget(self.aPIKeyLineEdit)

    def closeEvent(self, e):
        super().closeEvent(e)
        e.accept()


class MessageDialog(Dialog):
    def __init__(self):
        super(MessageDialog, self).__init__("ui/MessageDialog.ui")

    def closeEvent(self, e):
        super().closeEvent(e)
        e.accept()

if __name__ == "__main__":
    QCoreApplication.setOrganizationName("Fuzzwah")
    QCoreApplication.setApplicationName("LaMetric iRacing Data Sender")
    QCoreApplication.setOrganizationDomain("lametic-iracing.fuzzwah.com")

    qapp = QApplication(sys.argv)

    root = MainWindow()
    root.resize(800, 300)
    root.show()
    ret = qapp.exec_()
    sys.exit(ret)