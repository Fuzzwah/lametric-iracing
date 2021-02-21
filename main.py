#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pprint import pprint
from dataclasses import dataclass, field
from datetime import timedelta
from time import sleep
from random import random
import json
import traceback
from typing import Optional, List

import requests
from urllib3.exceptions import NewConnectionError, ConnectTimeoutError, MaxRetryError
from dataclasses_json import dataclass_json
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


@dataclass_json
@dataclass
class Frame:
    icon: str
    text: str


@dataclass_json
@dataclass
class Model:
    cycles: int
    frames: List[Frame]


@dataclass_json
@dataclass
class Notification:
    priority: str
    icon_type: str
    model: Model


@dataclass
class Driver(object):
    """
    a dataclass object to collect up the information about the driver
    """

    caridx: int = None
    name: str = None
    irating: int = None
    license_string: str = None
    license_letter: str = None
    safety_rating: float = None


@dataclass
class Data(object):
    """
    a dataclass object to collect up the data we need from the irsdk
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
    """
    a dataclass object to pass around information regarding the icons
    """

    ir: str = 'i43085'
    green_tick: str = 'a43780'
    spinner: str = 'a7660'

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
    """
    a dataclass object to pass around information regarding the current state
    """

    ir_connected: bool = False
    car_in_world: bool = False
    last_car_setup_tick: int = -1
    previous_events_sent: list = field(default_factory=list)
    cycles_start_shown: int = 0
    ratings_sent: bool = False
    previous_flag_notification_id: int = None


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
        super().__init__("ui/MainWindow_new.ui")

        self.setFixedWidth(400)
        self.setFixedHeight(140)

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
        self.register_widget(self.checkBox_BestLap, default=True)
        self.register_widget(self.checkBox_Flags, default=True)

        self.ir = IRSDK()
        self.state = State()
        self.sent_data = Data()
        self.data = Data()

        self.threadpool = QThreadPool()

        self.timerConnectionMonitor = QTimer()
        self.timerConnectionMonitor.setInterval(5000)
        self.timerConnectionMonitor.timeout.connect(self.irsdkConnectionMonitor)

        self.timerMainCycle = QTimer()
        self.timerMainCycle.setInterval(500)
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
        """
        Checks to see if the irsdk object is connected to the iRacing client
        """
        if self.state.ir_connected and not (self.ir.is_initialized and self.ir.is_connected):
            return False
        elif not self.state.ir_connected and self.ir.startup(silent=True) and self.ir.is_initialized and self.ir.is_connected:
            return True
        elif self.ir.is_initialized and self.ir.is_connected:
            return True

    def irsdk_connection_controller(self, now_connected):
        """
        Handles the triggering of things to do when the irsdk becomes connected / disconnected to the iRacing client
        """
        if now_connected and not self.state.ir_connected:
            self.onConnection()
        elif not now_connected and self.state.ir_connected:
            self.onDisconnection()

    def irsdkConnectionMonitor(self):
        """
        Sets up and kicks off the worker that monitors the state of the connection to the iRacing client
        """
        monitor_worker = Worker(self.irsdk_connection_check)
        monitor_worker.signals.result.connect(self.irsdk_connection_controller)

        self.threadpool.start(monitor_worker)

    def update_data(self, attr, value):
        """
        A little wrapper to handle updating the information in the Data object
        """
        try:
            setattr(self.data, attr, value)
        except KeyError:
            setattr(self.data, attr, None)

    def data_collection_cycle(self):
        """
        Runs on a loop that polls the iRacing client for driver data, flags, other info
        It loads the data into the data object and then the process_data function runs
        """
        if not self.irsdk_connection_check():
            self.irsdk_connection_controller(False)
        else:
            self.ir.freeze_var_buffer_latest()
            if self.ir['PlayerCarClassPosition'] > 0:
                self.update_data('position', f"{int(self.ir['PlayerCarClassPosition'])} / {int(len(self.ir['CarIdxClassPosition']))}")
            if self.ir['LapBestLapTime'] > 0:
                minutes, seconds = divmod(float(self.ir['LapBestLapTime']), 60)
                if seconds < 10:
                    bestlaptime = f"{minutes:.0f}:0{seconds:.3f}"
                else:
                    bestlaptime = f"{minutes:.0f}:{seconds:.3f}"
                print(bestlaptime)
                self.update_data('best_laptime', bestlaptime)
            if int(self.ir['LapCompleted']) > 0:
                if int(self.ir['LapCompleted']) + int(self.ir['SessionLapsRemainEx']) > 32000:
                    laps_total = "∞"
                else:
                    laps_total = int(self.ir['LapCompleted']) + int(self.ir['SessionLapsRemainEx'])
                self.update_data('laps', f"{int(self.ir['LapCompleted'])} / {laps_total}")
            self.update_data('flags', int(self.ir['SessionFlags']))
            self.ir.unfreeze_var_buffer_latest()

    def process_data(self):
        """
        Runs on a loop and processes the data stored in the data object
        Builds a list of events to send to the notification sender
        """
        events = []
        flag = False

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.start_hidden and self.state.cycles_start_shown < 20:
            self.state.cycles_start_shown += 1
            events.append(["start_hidden", "Start"])
            print(f"start_hidden: {self.data.flags} - {Flags.start_hidden}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.checkered:
            flag = True
            events.append(["checkered", "Finish"])
            print(f"checkered: {self.data.flags} - {Flags.checkered}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.white:
            flag = True
            events.append(["white", "White"])
            print(f"white: {self.data.flags} - {Flags.white}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.green:
            flag = True
            events.append(["green", "Green"])
            print(f"green: {self.data.flags} - {Flags.green}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.yellow:
            flag = True
            events.append(["yellow", "Yellow"])
            print(f"yellow: {self.data.flags} - {Flags.yellow}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.red:
            flag = True
            events.append(["red", "Red"])
            print(f"red: {self.data.flags} - {Flags.red}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.blue:
            flag = True
            events.append(["blue", "Blue"])
            print(f"blue: {self.data.flags} - {Flags.blue}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.debris:
            flag = True
            events.append(["debris", "Debris"])
            print(f"debris: {self.data.flags} - {Flags.debris}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.crossed:
            flag = True
            events.append(["crossed", "Crossed"])
            print(f"crossed: {self.data.flags} - {Flags.crossed}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.yellow_waving:
            flag = True
            events.append(["yellow_waving", "Yellow"])
            print(f"yellow_waving: {self.data.flags} - {Flags.yellow_waving}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.one_lap_to_green:
            flag = True
            events.append(["one_lap_to_green", "1 Lap"])
            print(f"one_lap_to_green: {self.data.flags} - {Flags.one_lap_to_green}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.green_held:
            flag = True
            events.append(["green_held", "Green"])
            print(f"green_held: {self.data.flags} - {Flags.green_held}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.ten_to_go:
            flag = True
            events.append(["ten_to_go", "10 to go"])
            print(f"ten_to_go: {self.data.flags} - {Flags.ten_to_go}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.five_to_go:
            flag = True
            events.append(["five_to_go", "5 to go"])
            print(f"five_to_go: {self.data.flags} - {Flags.five_to_go}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.random_waving:
            flag = True
            events.append(["random_waving", "Random"])
            print(f"random_waving: {self.data.flags} - {Flags.random_waving}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.caution:
            flag = True
            events.append(["caution", "Caution"])
            print(f"caution: {self.data.flags} - {Flags.caution}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.caution_waving:
            flag = True
            events.append(["caution_waving", "Caution"])
            print(f"caution_waving: {self.data.flags} - {Flags.caution_waving}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.black:
            flag = True
            events.append(["black", "Black"])
            print(f"black: {self.data.flags} - {Flags.black}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.disqualify:
            flag = True
            events.append(["disqualify", "DQ"])
            print(f"disqualify: {self.data.flags} - {Flags.disqualify}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.furled:
            flag = True
            events.append(["furled", "Warning"])
            print(f"furled: {self.data.flags} - {Flags.furled}")

        if self.checkBox_Flags.isChecked() and self.data.flags & Flags.repair:
            flag = True
            events.append(["repair", "Damage"])
            print(f"repair: {self.data.flags} - {Flags.repair}")

        if self.data.best_laptime:
            if self.sent_data.best_laptime != self.data.best_laptime:
                print("new best lap")
            if self.checkBox_BestLap.isChecked() and not flag and self.sent_data.best_laptime != self.data.best_laptime and self.data.best_laptime:
                self.lineEdit_BestLap.setText(self.data.best_laptime)
                events.append(["purple", self.data.best_laptime])
        
        if self.data.position:
            if self.checkBox_Position.isChecked() and not flag and self.sent_data.position != self.data.position:
                self.lineEdit_Position.setText(f"{self.data.position}")
                event = "gain_position"
                if self.sent_data.position:
                    if self.sent_data.position < self.data.position:
                        event = "lose_position"
                events.append([event, f"{self.data.position}"])

        if self.data.laps:
            if self.sent_data.laps != self.data.laps:
                print("new lap")
            if self.checkBox_Laps.isChecked() and not flag and self.sent_data.laps != self.data.laps:
                self.lineEdit_Laps.setText(f"{self.data.laps}")
                events.append(['laps', f"{self.data.laps}"])

        if len(events) > 0:
            print(events)
            if flag:
                self.send_notification(events, flag=True)
            else:
                if self.state.previous_flag_notification_id:
                    self.dismiss_notification(self.state.previous_flag_notification_id)
                self.send_notification(events, cycles=2)
            self.sent_data = self.data
        else:
            if self.state.previous_flag_notification_id:
                self.dismiss_notification(self.state.previous_flag_notification_id)

    def main_cycle(self):
        """
        Sets up and kicks off the worker collects data from the iRacing client and then processes it
        """
        main_cycle_worker = Worker(self.data_collection_cycle)
        main_cycle_worker.signals.result.connect(self.process_data)

        self.threadpool.start(main_cycle_worker)

    def onConnection(self):
        """
        When the connection to iRacing client becomes active, this function runs
        It updates the status bar, grabs initial driver info, triggers to endless ratings notifications, and starts the main cycle loop
        """
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

                break

        self.lineEdit_IRating.setText(f"{self.driver.irating:,}")
        self.lineEdit_License.setText(self.driver.license_string)

        self.send_ratings()

        self.timerMainCycle.start()

    def onDisconnection(self):
        """
        When the connection to iRacing client is lost, this function runs
        Updates the status bar, stops the main cycle
        """
        self.state = State()
        self.ir.shutdown()

        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')
        self.timerMainCycle.stop()
        self.timerConnectionMonitor.start()

    def send_ratings(self):
        """
        A wrapper that builds the events list containing iRating and License / SR info, and triggers the notification send
        """
        if not self.state.ratings_sent:
            events = []

            if self.checkBox_IRating.isChecked():
                events.append(["ir", f"{self.driver.irating:,}"])

            if self.checkBox_License.isChecked():
                icon = "ir"
                if self.driver.license_letter == 'R':
                    icon = "license_letter_r"
                elif self.driver.license_letter == 'D':
                    icon = "license_letter_d"
                elif self.driver.license_letter == 'C':
                    icon = "license_letter_c"
                elif self.driver.license_letter == 'B':
                    icon = "license_letter_b"
                elif self.driver.license_letter == 'A':
                    icon = "license_letter_a"
                elif self.driver.license_letter == 'P':
                    icon = "license_letter_p"

                events.append([icon, f"{self.driver.safety_rating}"])

            if len(events) > 0:
                self.send_notification(events, priority='info', ratings=True)

    def dismiss_notification(self, notification_id):
        """
        Dismisses a notification
        """

        res = self.call_lametric_api("delete", notification_id=notification_id)
        print(res)

    def send_notification(self, events, priority="critical", cycles=0, ratings=False, flag=False):
        """
        Accepts a list of events and packages them up into json and triggers the sending of a notification via LaMetic API
        """
        events_to_send = []

        data = {
            "priority": priority,
            "icon_type":"none",
            "model": {
                "cycles": cycles,
                "frames": []
            }
        }

        for event, text in events:
            events_to_send.append((event, text))
            icon = getattr(Icons, event)
            data["model"]["frames"].append({"icon": icon, "text": text})

        if sorted(events_to_send) != sorted(self.state.previous_events_sent):
            if len(data["model"]["frames"]) > 0:
                res = self.call_lametric_api("send", data=data)
                try:
                    notification_id = res['success']['id']
                except KeyError:
                    notification_id = None
                finally:
                    self.state.previous_events_sent = events_to_send
                    if ratings:
                        self.state.ratings_sent = True
                    elif flag:
                        self.state.previous_flag_notification_id = notification_id

    def call_lametric_api(self, endpoint, data=None, notification_id=None):
        """
        The function that handles all interactions (send, list queue, delete from queue) with the LaMetric clock via API calls
        """
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
            if endpoint == "delete":
                lametric_url = f"{lametric_url}/{notification_id}"
            headers = {"Content-Type": "application/json; charset=utf-8"}
            basicAuthCredentials = ("dev", self.lametric_api_key)
            try:
                response = False
                if endpoint == "send":
                    response = requests.post(
                        lametric_url,
                        headers=headers,
                        auth=basicAuthCredentials,
                        json=data,
                        timeout=1,
                    )
                elif endpoint == "queue":
                    response = requests.get(
                        lametric_url,
                        headers=headers,
                        auth=basicAuthCredentials,
                        timeout=1,
                    )
                elif endpoint == "delete":
                    response = requests.delete(
                        lametric_url,
                        headers=headers,
                        auth=basicAuthCredentials,
                        timeout=1,
                    )
                if response:
                    return json.loads(response.text)
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

    def show_settings(self):
        """
        Triggers the opening of the settings window
        """
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
        """
        What to do when the test button is clicked
        """

        pprint(self.state)


    def closeEvent(self, e):
        """
        When the application is closed, these tasks will be completed
        """
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