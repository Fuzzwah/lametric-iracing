#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pprint import pprint
from dataclasses import dataclass
from time import sleep
import json
from typing import Optional, List, Dict

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import NewConnectionError, ConnectTimeoutError, MaxRetryError
from dataclasses_json import dataclass_json
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import (
    QCoreApplication,
    QObject,
    QThread,
    QSettings,
    pyqtSlot,
    pyqtSignal
)
from window import Window, Dialog
from pyirsdk import (
    IRSDK,
    Flags
)

disable_warnings()

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
    one_lap_to_green: str = 'i43445'
    random_waving: str = 'a43458'
    caution: str = 'i43439'
    caution_waving: str = 'a43439'
    black: str = 'a43499'
    disqualify: str = 'a43492'
    furled: str = 'a43496'
    repair: str = 'a43500'
    # we don't have icons for these yet
    crossed: str = ir
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
    previous_data_sent: Dict = None
    start_hidden_shown: bool = False
    ratings_sent: bool = False


class ConnectToIRacing(QObject):
    """
    The worker that monitors if the app is connected to iRacing
    """

    connected_to_iracing = pyqtSignal()

    def __init__(self):
        super(ConnectToIRacing, self).__init__()

        self.ir = IRSDK()
                
    def run(self):
        while not self.ir.is_initialized and not self.ir.is_connected:
            self.ir.startup(silent=True)
            if not self.ir.is_initialized and not self.ir.is_connected:
                sleep(5)
        else:
            self.ir.shutdown()
            self.connected_to_iracing.emit()


def call_lametric_api(endpoint, data=None, notification_id=None):
    """
    The function that handles all interactions with the LaMetric clock via API calls
    Available endpoints are:
        send - to send a notification (must include data)
        delete - to delete or dismiss a notification (must include notification_id)
        queue - returns a list of current notifications in the queue
    """
    s = QSettings()
    try:
        lametric_ip = s.value('lametric-iracing/Settings/laMetricTimeIPLineEdit')
    except:
        lametric_ip = None
    try:
        lametric_api_key = s.value('lametric-iracing/Settings/aPIKeyLineEdit')
    except:
        lametric_api_key = None

    if lametric_ip and lametric_api_key:
        lametric_url = f"https://{lametric_ip}:4343/api/v2/device/notifications"
        if endpoint == "delete":
            lametric_url = f"{lametric_url}/{notification_id}"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        auth_creds = ("dev", lametric_api_key)
        try:
            response = False
            if endpoint == "send":
                if data:
                    response = requests.post(
                        lametric_url,
                        headers=headers,
                        auth=auth_creds,
                        json=data,
                        timeout=1,
                        verify=False
                    )
            if endpoint == "queue":
                response = requests.get(
                    lametric_url,
                    headers=headers,
                    auth=auth_creds,
                    timeout=1,
                    verify=False
                )
            if endpoint == "delete":
                response = requests.delete(
                    lametric_url,
                    headers=headers,
                    auth=auth_creds,
                    timeout=1,
                    verify=False
                )
            if response:
                res = json.loads(response.text)
                return res
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

class MainCycle(QObject):
    """
    The worker that gets the data from iRacing and processes it
    Updates GUI via signals
    Sends notifications to LaMetric device
    """

    disconnected_from_iracing = pyqtSignal()
    irating_update = pyqtSignal(str)
    license_update = pyqtSignal(str)
    laps_update = pyqtSignal(str)
    best_laptime_update = pyqtSignal(str)
    position_update = pyqtSignal(str)

    def __init__(self, enable_irating, enable_license, enable_flags, enable_laps, enable_bestlap, enable_position):
        super(MainCycle, self).__init__()

        self.ir = IRSDK()
        self.state = State()
        self.sent_data = Data()
        self.data = Data()
        self.driver = Driver()

        self.enable_irating = enable_irating
        self.enable_license = enable_license
        self.enable_flags = enable_flags
        self.enable_laps = enable_laps
        self.enable_bestlap = enable_bestlap
        self.enable_position = enable_position

    def run(self):
        self.ir.startup(silent=True)
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

        self.irating_update.emit(f"{self.driver.irating:,}")
        self.license_update.emit(self.driver.license_string)

        self.dismiss_all_notifications()
        self.send_ratings()

        while self.ir.is_initialized and self.ir.is_connected:
            self.data_collection()
            self.process_data()
            sleep(0.3)
            if not self.ir.is_initialized and not self.ir.is_connected:
                break
        else:
            self.ir.shutdown()
            self.disconnected_from_iracing.emit()

    def update_data(self, attr, value):
        """
        A little wrapper to handle updating the information in the Data object
        """
        try:
            setattr(self.data, attr, value)
        except KeyError:
            setattr(self.data, attr, None)

    def data_collection(self):
        """
        Runs on a loop that polls the iRacing client for driver data, flags, other info
        It loads the data into the data object and then the process_data function runs
        """
        self.ir.freeze_var_buffer_latest()
        if self.ir['PlayerCarClassPosition'] > 0:
            self.update_data('position', f"{int(self.ir['PlayerCarClassPosition'])} / {int(len(self.ir['CarIdxClassPosition']))}")
        if self.ir['LapBestLapTime'] > 0:
            minutes, seconds = divmod(float(self.ir['LapBestLapTime']), 60)
            if seconds < 10:
                bestlaptime = f"{minutes:.0f}:0{seconds:.3f}"
            else:
                bestlaptime = f"{minutes:.0f}:{seconds:.3f}"
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
        Builds a list of frames to send to the notification sender
        """
        frames = []
        flag = False

        if self.enable_flags:

            if self.data.flags & Flags.start_hidden and not self.state.start_hidden_shown:
                self.state.start_hidden_shown = True
                frames.append(Frame(Icons.start_hidden, "Start"))

            if self.data.flags & Flags.checkered:
                flag = True
                frames.append(Frame(Icons.checkered, "Finish"))

            if self.data.flags & Flags.white:
                flag = True
                frames.append(Frame(Icons.white, "White"))

            if self.data.flags & Flags.green:
                flag = True
                frames.append(Frame(Icons.green, "Green"))

            if self.data.flags & Flags.yellow:
                flag = True
                frames.append(Frame(Icons.yellow, "Yellow"))

            if self.data.flags & Flags.red:
                flag = True
                frames.append(Frame(Icons.red, "Red"))

            if self.data.flags & Flags.blue:
                flag = True
                frames.append(Frame(Icons.blue, "Blue"))

            if self.data.flags & Flags.debris:
                flag = True
                frames.append(Frame(Icons.debris, "Debris"))

            if self.data.flags & Flags.crossed:
                flag = True
                frames.append(Frame(Icons.crossed, "Crossed"))

            if self.data.flags & Flags.yellow_waving:
                flag = True
                frames.append(Frame(Icons.yellow_waving, "Yellow"))

            if self.data.flags & Flags.one_lap_to_green:
                flag = True
                frames.append(Frame(Icons.one_lap_to_green, "in 1 lap"))

            if self.data.flags & Flags.green_held:
                flag = True
                frames.append(Frame(Icons.green_held, "Green"))

            if self.data.flags & Flags.ten_to_go:
                flag = True
                frames.append(Frame(Icons.ten_to_go, "10 to go"))

            if self.data.flags & Flags.five_to_go:
                flag = True
                frames.append(Frame(Icons.five_to_go, "5 to go"))

            if self.data.flags & Flags.random_waving:
                flag = True
                frames.append(Frame(Icons.random_waving, "Random"))

            if self.data.flags & Flags.caution:
                flag = True
                frames.append(Frame(Icons.caution, "Caution"))

            if self.data.flags & Flags.caution_waving:
                flag = True
                frames.append(Frame(Icons.caution_waving, "Caution"))

            if self.data.flags & Flags.black:
                flag = True
                frames.append(Frame(Icons.black, "Black"))

            if self.data.flags & Flags.disqualify:
                flag = True
                frames.append(Frame(Icons.disqualify, "DQ"))

            if self.data.flags & Flags.furled:
                flag = True
                frames.append(Frame(Icons.furled, "Warning"))

            if self.data.flags & Flags.repair:
                flag = True
                frames.append(Frame(Icons.repair, "Damage"))

        if self.data.best_laptime:
            if not flag and self.sent_data.best_laptime != self.data.best_laptime:
                self.best_laptime_update.emit(self.data.best_laptime)
                if self.enable_bestlap:
                    frames.append(Frame(Icons.purple, self.data.best_laptime))
        
        if self.data.position:
            if not flag and self.sent_data.position != self.data.position:
                self.position_update.emit(f"{self.data.position}")
                icon = Icons.gain_position
                if self.sent_data.position:
                    if self.sent_data.position < self.data.position:
                        icon = Icons.lose_position
                if self.enable_position:
                    frames.append(Frame(icon, f"{self.data.position}"))

        if self.data.laps:
            if not flag and self.sent_data.laps != self.data.laps:
                self.laps_update.emit(f"{self.data.laps}")
                if self.enable_laps:
                    frames.append(Frame(Icons.laps, f"{self.data.laps}"))

        if len(frames) > 0:
            if flag:
                notification_obj = Notification('critical', 'none', Model(0, frames))
                self.send_notification(notification_obj)
            else:
                notification_obj = Notification('critical', 'none', Model(1, frames))
                self.send_notification(notification_obj)
            self.sent_data = self.data
        sleep(0.2)

    def send_ratings(self):
        """
        A wrapper that builds the frames list containing iRating and License / SR info, and triggers the notification send
        """
        frames = []

        self.irating_update.emit(f"{self.driver.irating:,}")
        if self.enable_irating:
            frames.append(Frame(Icons.ir, f"{self.driver.irating:,}"))

        self.license_update.emit(f"{self.driver.safety_rating}")
        if self.enable_license:
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
            frames.append(Frame(icon, f"{self.driver.safety_rating}"))

            notification_obj = Notification('info', 'none', Model(0, frames))
            self.send_notification(notification_obj)

    def dismiss_all_notifications(self):
        """
        Dismisses all notifications
        """

        queue = call_lametric_api("queue")

        if queue:
            for notification in queue:
                self.dismiss_notification(notification['id'])
                sleep(0.1)            

    def dismiss_prior_notifications(self):
        """
        Dismisses any notifications prior to the new one we just sent
        """

        queue = call_lametric_api("queue")

        if queue:
            del queue[-1]
            pprint(queue)

            for notification in queue:
                if notification['priority'] == 'critical':
                    self.dismiss_notification(notification['id'])
                    sleep(0.1)            

    def dismiss_notification(self, notification_id):
        """
        Dismisses a single notification by id
        """

        print(f"dismissing {notification_id}")
        res = call_lametric_api("delete", notification_id=notification_id)
        if res:
            return res['success']
        else:
            return False

    def send_notification(self, notification_obj):
        """
        Accepts a Notification object triggers the sending of a notification via LaMetic API
        Note: the function will not send the same notification multiple times in a row
        """
 
        data = notification_obj.to_dict()
        pprint(self.state.previous_data_sent)
        pprint(data)
        if data != self.state.previous_data_sent:
            res = call_lametric_api("send", data=data)
            if "success" in res:
                self.dismiss_prior_notifications()
                self.state.previous_data_sent = data
            return True


class MainWindow(Window):
    def __init__(self):
        super().__init__("ui/MainWindow.ui")

        self.setFixedWidth(400)
        self.setFixedHeight(140)

        self.settings_dialog: Optional[SettingsDialog] = None

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

        self.connection_thread = QThread()
        self.connection_worker = ConnectToIRacing()
        self.connection_worker.moveToThread(self.connection_thread)
        self.connection_thread.started.connect(self.connection_worker.run)
        self.connection_worker.connected_to_iracing.connect(self.connection_thread.quit)
        self.connection_worker.connected_to_iracing.connect(self.connected_to_iracing)
        self.connection_thread.start()

    def connected_to_iracing(self):
           
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(0,150,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage(('STATUS: iRacing client detected.'))

        enable_irating = self.checkBox_IRating.isChecked()
        enable_license = self.checkBox_License.isChecked()
        enable_flags = self.checkBox_Flags.isChecked()
        enable_laps = self.checkBox_Laps.isChecked()
        enable_bestlap = self.checkBox_BestLap.isChecked()
        enable_position = self.checkBox_Position.isChecked()

        self.main_thread = QThread()
        self.main_worker = MainCycle(enable_irating, enable_license, enable_flags, enable_laps, enable_bestlap, enable_position)
        self.main_worker.moveToThread(self.main_thread)
        self.main_thread.started.connect(self.main_worker.run)
        self.main_worker.disconnected_from_iracing.connect(self.main_thread.quit)
        self.main_worker.disconnected_from_iracing.connect(self.disconnected_from_iracing)
        self.main_worker.irating_update.connect(self.update_irating)
        self.main_worker.license_update.connect(self.update_license)
        self.main_worker.laps_update.connect(self.update_laps)
        self.main_worker.best_laptime_update.connect(self.update_best_laptime)
        self.main_worker.position_update.connect(self.update_position)
        self.main_thread.start()

    def update_irating(self, irating_str):
        self.lineEdit_IRating.setText(irating_str)

    def update_license(self, license_str):
        self.lineEdit_License.setText(license_str)

    def update_laps(self, laps_str):
        self.lineEdit_Laps.setText(laps_str)

    def update_best_laptime(self, best_laptime_str):
        self.lineEdit_BestLap.setText(best_laptime_str)

    def update_position(self, position_str):
        self.lineEdit_Position.setText(position_str)

    def disconnected_from_iracing(self):

        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')

    def check_settings(self):
        s = QSettings()
        try:
            self.lametric_ip = s.value('lametric-iracing/Settings/laMetricTimeIPLineEdit')
        except:
            self.lametric_ip = None
        try:
            self.lametric_api_key = s.value('lametric-iracing/Settings/aPIKeyLineEdit')
        except:
            self.lametric_api_key = None

        if not self.lametric_ip or not self.lametric_api_key:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Please configure the settings")
            msg.setText("Please use the Settings window to configure this application with the IP address of our LaMetric Time clock and it's API key.")
            msg.exec_()
            self.open_settings_dialog()

    @pyqtSlot()
    def on_settingsButton_clicked(self):
        self.open_settings_dialog()

    def open_settings_dialog(self):
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog()

        self.settings_dialog.show()

    @pyqtSlot()
    def on_testButton_clicked(self):
        """
        What to do when the test button is clicked
        """
        queue = call_lametric_api("queue")

        notification_obj = Notification('info', 'none', Model(2, [Frame(Icons.green_tick, 'Success')]))
        data = notification_obj.to_dict()
        res = call_lametric_api("send", data=data)
        if res:
            if "success" in res:        
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Test Send Results")
                msg.setText("Successfully sent the test notification to your LaMetric Time clock.\n\nYou're ready to go!")
                msg.exec_()
                return True

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Test Send Results")
        msg.setText("Failed to send the test notification to your LaMetric Time clock. \n\nPlease check the Settings window and ensure that you have the correct IP address and API key.")
        msg.exec_()

    def closeEvent(self, e):
        """
        When the application is closed, these tasks will be completed
        """
        super().closeEvent(e)
        try:
            self.connection_thread.quit()
        except:
            pass
        try:
            self.main_thread.quit()
        except:
            pass
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

if __name__ == "__main__":
    QCoreApplication.setOrganizationName("Fuzzwah")
    QCoreApplication.setApplicationName("LaMetric iRacing Data Sender")
    QCoreApplication.setOrganizationDomain("lametic-iracing.fuzzwah.com")

    qapp = QApplication(sys.argv)

    root = MainWindow()
    root.resize(800, 300)
    root.show()
    root.check_settings()
    ret = qapp.exec_()
    sys.exit(ret)