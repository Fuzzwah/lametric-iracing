#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pprint import pprint
from dataclasses import dataclass, fields, asdict
from time import sleep
import json
from typing import Optional, List, Dict

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import NewConnectionError, ConnectTimeoutError, MaxRetryError
from dataclasses_json import dataclass_json
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QMessageBox, QComboBox
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
    Flags,
    SessionState,
    TrkLoc,
    TrkSurf
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

def copy_data(from_obj, to_obj):
    for field in fields(Data):
        setattr(to_obj, field.name, getattr(from_obj, field.name))    

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
    a dataclass object to collect up the data we need from the IRSDK
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
class SessionTypes(object):
    practice: str = "Practice"
    qualify: str = "Qualify"
    lonequalify: str = "Lone Qualify"
    race: str = "Race"


@dataclass(frozen=True)
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
    position: str = '44149'
    gain_position: str = 'a43651'
    lose_position: str = 'a43652'


@dataclass()
class Car(object):
    CarIdx: int = None
    CarClassID: int = None
    CarNumber: int = None
    ClassPosition: int = None
    UserID: int = None
    DriverName: str = None
    GapAhead: float = None
    GapBehind: float = None
    GapSortedBy: float = None
    LiveLaps: float = None
    LivePosition: int = None
    TeamName: str = None
    WeightBase: float = 1
    WeightCurrent: float = 1


@dataclass
class State(object):
    """
    a dataclass object to pass around information regarding the current state
    """

    ir_connected: bool = False
    previous_data_sent: Dict = None
    start_hidden_shown: bool = False


@dataclass
class Options(object):
    """
    a dataclass object to pass around the current options selected in the UI
    """

    enable_irating: bool = True
    enable_license: bool = True
    enable_flags: bool = True
    enable_laps: bool = True
    enable_bestlap: bool = True
    enable_position: bool = True
    default_display: str = "ratings"


class MainWorkerSignals(QObject):
    connected_to_iracing = pyqtSignal()
    disconnected_from_iracing = pyqtSignal()
    irating_update = pyqtSignal(str)
    license_update = pyqtSignal(str)
    laps_update = pyqtSignal(str)
    best_laptime_update = pyqtSignal(str)
    position_update = pyqtSignal(str)


class MainWorker(QThread):
    def __init__(self, parent=None):
        QThread.__init__(self, parent)

        self.ir = IRSDK()
        self.state = State()
        self.sent_data = Data()
        self.data = Data()
        self.driver = Driver()
        self.cars = {}

        self.signals = MainWorkerSignals()
        self.options = Options()

        self.signals.connected_to_iracing.connect(parent.connected_to_iracing)
        self.signals.disconnected_from_iracing.connect(parent.disconnected_from_iracing)
        self.signals.irating_update.connect(parent.update_irating)
        self.signals.license_update.connect(parent.update_license)
        self.signals.laps_update.connect(parent.update_laps)
        self.signals.best_laptime_update.connect(parent.update_best_laptime)
        self.signals.position_update.connect(parent.update_position)

        self._active = False

    def get_sessiontype(self):
        """
        What type of session is this?
        """
        session_type = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']]['SessionType']
        return session_type

    def get_sessionstate(self):
        """
        What session state is this?
        """
        session_state = self.ir['SessionState']
        return session_state

    def is_practice_session(self):
        """
        Is this session Practice?
        """
        session_type = self.get_sessiontype()
        if session_type == SessionTypes.practice:
            return True
        else:
            return False

    def is_qualify_session(self):
        """
        Is this session Racing?
        """
        session_type = self.get_sessiontype()
        if session_type == SessionTypes.qualify or session_type == SessionTypes.lonequalify:
            return True
        else:
            return False

    def is_race_session(self):
        """
        Is this session Racing?
        """
        session_type = self.get_sessiontype()
        if session_type == SessionTypes.race:
            return True
        else:
            return False

    def is_get_in_car_sessionstate(self):
        """
        Is it currently time to get in the car?
        """
        if self.ir['SessionState'] == SessionState.get_in_car:
            return True
        else:
            return False

    def is_warmup_sessionstate(self):
        """
        Is it currently warmup?
        """
        if self.ir['SessionState'] == SessionState.warmup:
            return True
        else:
            return False

    def is_parade_laps_sessionstate(self):
        """
        Is it currently parade laps?
        """
        if self.ir['SessionState'] == SessionState.parade_laps:
            return True
        else:
            return False

    def is_racing_sessionstate(self):
        """
        Is it currently a race?
        """
        if self.ir['SessionState'] == SessionState.racing:
            return True
        else:
            return False

    def is_checkered_sessionstate(self):
        """
        Is it currently checkered?
        """
        if self.ir['SessionState'] == SessionState.checkered:
            return True
        else:
            return False

    def is_cool_down_sessionstate(self):
        """
        Is it currently cool down?
        """
        if self.ir['SessionState'] == SessionState.cool_down:
            return True
        else:
            return False

    def is_race_session_pre_racing_sessionstate(self):
        """
        Is it currently before racing?
        """
        if self.ir['SessionState'] in [SessionState.get_in_car, SessionState.warmup, SessionState.parade_laps]:
            return True
        else:
            return False

    def get_sessionstate_name(self):
        """
        Is it currently before racing?
        """
        if self.is_get_in_car_sessionstate():
            return "Get In Car"
        elif self.is_warmup_sessionstate():
            return "Warm Up"
        elif self.is_parade_laps_sessionstate():
            return "Parade Lap"
        elif self.is_racing_sessionstate():
            return "Racing"
        elif self.is_checkered_sessionstate():
            return "Checkered"
        elif self.is_cool_down_sessionstate():
            return "Cool Down"
        else:
            return "Unknown"

    def default_display(self, selected):
        self.options.default_display = selected

    def enable_irating(self, state):
        self.options.enable_irating = state

    def enable_license(self, state):
        self.options.enable_license = state

    def enable_flags(self, state):
        self.options.enable_flags = state

    def enable_laps(self, state):
        self.options.enable_laps = state

    def enable_position(self, state):
        self.options.enable_position = state

    def enable_bestlap(self, state):
        self.options.enable_bestlap = state

    def deactivate(self):
        self._active = False

    def connected(self):
        for dvr in self.ir['DriverInfo']['Drivers']:
            if dvr['CarIdx'] == self.ir['DriverInfo']['DriverCarIdx']:
                self.driver.caridx = dvr['CarIdx']
                self.driver.name = dvr['UserName']
                self.driver.irating = int(dvr['IRating'])
                self.driver.license_string = dvr['LicString']
                license_letter, safety_rating = dvr['LicString'].split(' ')
                self.driver.license_letter = license_letter
                self.driver.safety_rating = float(safety_rating)        
        self.dismiss_notifications()
        self.send_ratings()
        self.signals.connected_to_iracing.emit()
        self.state.ir_connected = True
        self.state.start_hidden_shown = False

    def run(self):
        self._active = True
        # Do something on the worker thread
        while self._active:
            if self.ir.is_initialized and self.ir.is_connected:
                if not self.state.ir_connected:
                    self.connected()

                self.data_collection()
                self.calculate_positions()
                pprint(self.cars)
                self.process_data()

            else:
                if self.state.ir_connected:
                    self.signals.disconnected_from_iracing.emit()
                    self.state.ir_connected = False
                self.ir.startup(silent=True)
                for i in range(50):
                    if self._active:
                        sleep(0.1)

    def calculate_positions(self):
        if self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']]['ResultsPositions']:
            results = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']]['ResultsPositions']
        # if no laps have been completed in this session, we will use the list of drivers from the previous session
        elif self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']-1]['ResultsPositions']:
            results = self.ir['SessionInfo']['Sessions'][self.ir['SessionNum']-1]['ResultsPositions']
        else:
            results = []        

        if len(results) > 0:
            for car in results:
                if car['ReasonOutId'] == 0:
                    fullname = self.ir['DriverInfo']['Drivers'][car['CarIdx']]['UserName']
                    namelist = fullname.split(" ")
                    outlist = []
                    outlist.append(namelist[0][0:1])
                    lastname = str(namelist[-1])
                    if lastname.lower() in ["jr", "ii", "iii"]:
                        lastname = namelist[-2]
                    outlist.append(lastname)
                    initialname = '.'.join(outlist)

                    if car['CarIdx'] not in self.cars:
                        self.cars[car['CarIdx']] = asdict(Car())

                    if self.ir['CarIdxLap'][car['CarIdx']] == 1 or self.ir['CarIdxLapDistPct'][car['CarIdx']] == 1:
                        livelaps = car['LapsComplete']
                    else:
                        # a hack to work around the fact that iRacing uses 0 for both the lap before s/f and lap after s/f when the session goes green
                        if self.is_race_session_pre_racing_sessionstate() and self.ir['CarIdxLapDistPct'][car['CarIdx']] > 0.5:
                            livelaps = self.ir['CarIdxLapDistPct'][car['CarIdx']] - 1
                        else:
                            if self.cars[car['CarIdx']]['LiveLaps'] and self.cars[car['CarIdx']]['LiveLaps'] < 0 and self.ir['CarIdxLapDistPct'][car['CarIdx']] > 0.5:
                                livelaps = self.ir['CarIdxLapDistPct'][car['CarIdx']] - 1
                            else:
                                livelaps = self.ir['CarIdxLap'][car['CarIdx']] + self.ir['CarIdxLapDistPct'][car['CarIdx']]

                    self.cars[car['CarIdx']]['CarIdx'] = int(car['CarIdx'])
                    self.cars[car['CarIdx']]['CarClassID'] = str(self.ir['DriverInfo']['Drivers'][car['CarIdx']]['CarClassID'])
                    self.cars[car['CarIdx']]['CarNumber'] = str(self.ir['DriverInfo']['Drivers'][car['CarIdx']]['CarNumber'])
                    self.cars[car['CarIdx']]['ClassPosition'] = int(car['ClassPosition'] + 1)
                    self.cars[car['CarIdx']]['UserID'] = int(self.ir['DriverInfo']['Drivers'][car['CarIdx']]['UserID'])
                    self.cars[car['CarIdx']]['DriverName'] = initialname
                    self.cars[car['CarIdx']]['LiveLaps'] = livelaps
                    self.cars[car['CarIdx']]['TeamName'] = str(self.ir['DriverInfo']['Drivers'][car['CarIdx']]['TeamName'])

            return True
        return False

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
        
        if int(self.ir['PlayerCarClassPosition']) > 0:
            self.update_data('position', f"{int(self.ir['PlayerCarClassPosition'])} / {int(len(self.ir['DriverInfo']['Drivers']))}")
        else:
            self.update_data('position', f"{int(len(self.ir['DriverInfo']['Drivers']))} / {int(len(self.ir['DriverInfo']['Drivers']))}")
        
        if float(self.ir['LapBestLapTime']) > 0:
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

        if self.options.enable_flags:

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
                frames.append(Frame(Icons.furled, "Warn"))

            if self.data.flags & Flags.repair:
                flag = True
                frames.append(Frame(Icons.repair, "Damage"))

        if self.data.best_laptime:
            if not flag and self.sent_data.best_laptime != self.data.best_laptime:
                self.signals.best_laptime_update.emit(self.data.best_laptime)
                if self.options.enable_bestlap:
                    frames.append(Frame(Icons.purple, self.data.best_laptime))
        
        if self.data.position:
            if not flag and self.sent_data.position != self.data.position:
                self.signals.position_update.emit(f"{self.data.position}")
                icon = Icons.gain_position
                if self.sent_data.position:
                    if self.sent_data.position < self.data.position:
                        icon = Icons.lose_position
                if self.options.enable_position:
                    frames.append(Frame(icon, f"{self.data.position}"))

        if self.data.laps:
            if not flag and self.sent_data.laps != self.data.laps:
                self.signals.laps_update.emit(f"{self.data.laps}")
                if self.options.enable_laps:
                    frames.append(Frame(Icons.laps, f"{self.data.laps}"))

        if len(frames) > 0:
            if flag:
                notification_obj = Notification('critical', 'none', Model(0, frames))
                self.send_notification(notification_obj)
            else:
                notification_obj = Notification('critical', 'none', Model(1, frames))
                self.send_notification(notification_obj)
            copy_data(self.data, self.sent_data)
        else:
            self.send_default_display()
        sleep(0.2)

    def send_default_display(self):
        if self.options.default_display == "ratings":
            if not self.send_ratings():
                self.dismiss_notifications()
        elif self.options.default_display == "position":
            notification_obj = Notification('info', 'none', Model(0, [Frame(Icons.position, f"{self.data.position}")]))
            self.send_notification(notification_obj)
        elif self.options.default_display == "laps":
            notification_obj = Notification('info', 'none', Model(0, [Frame(Icons.laps, f"{self.data.laps}")]))
            self.send_notification(notification_obj)
        elif self.options.default_display == "bestlaps":
            notification_obj = Notification('info', 'none', Model(0, [Frame(Icons.purple, f"{self.data.best_laptime}")]))
            self.send_notification(notification_obj)

    def send_ratings(self):
        """
        A wrapper that builds the frames list containing iRating and License / SR info, and triggers the notification send
        """
        frames = []

        self.signals.irating_update.emit(f"{self.driver.irating:,}")
        if self.options.enable_irating:
            frames.append(Frame(Icons.ir, f"{self.driver.irating:,}"))

        self.signals.license_update.emit(f"{self.driver.safety_rating}")
        if self.options.enable_license:
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

        if len(frames) > 0:
            if self.options.default_display == "ratings":
                cycles = 0
            else:
                cycles = 2
            notification_obj = Notification('info', 'none', Model(cycles, frames))
            self.send_notification(notification_obj)
            return True
        else:
            return False

    def dismiss_notifications(self, excluding=None):
        """
        Dismisses any notifications prior to the new one we just sent
        """

        queue = call_lametric_api("queue")

        if queue:
            for notification in queue:
                if notification['id'] != excluding and notification['model']['cycles'] == 0:
                    self.dismiss_notification(notification['id'])
                    sleep(0.1)            

    def dismiss_notification(self, notification_id):
        """
        Dismisses a single notification by id
        """

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
        if data != self.state.previous_data_sent:
            res = call_lametric_api("send", data=data)
            try:
                if "success" in res:
                    notification_id = res['success']['id']
                    self.dismiss_notifications(excluding=notification_id)
                    self.state.previous_data_sent = data
                return True
            except TypeError:
                # need a message that send failed
                return False

class MainWindow(Window):
    def __init__(self):
        super().__init__("ui/MainWindow.ui")

        self.setFixedWidth(400)
        self.setFixedHeight(190)

        self.settings_dialog: Optional[SettingsDialog] = None
        
        #s = QSettings()
        #s.clear()

        sb = self.statusBar()
        sb.setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        sb.setFixedHeight(20)
        self.setStatusBar(sb)
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')

        self.default_display_options = {
            0: ("Cycle iR/License", 'ratings'),
            1: ("Position", 'position'),
            2: ("Laps", 'laps'),
            3: ("Best Lap", 'bestlap'),
        }

        self.register_widget(self.comboBox_DefaultDisplay, default="Cycle iR/License", changefunc=self.new_default_display)
        self.register_widget(self.checkBox_IRating, default=True, changefunc=self.toggled_irating)
        self.register_widget(self.checkBox_License, default=True, changefunc=self.toggled_license)
        self.register_widget(self.checkBox_Position, default=True, changefunc=self.toggled_position)
        self.register_widget(self.checkBox_Laps, default=True, changefunc=self.toggled_laps)
        self.register_widget(self.checkBox_BestLap, default=True, changefunc=self.toggled_bestlap)
        self.register_widget(self.checkBox_Flags, default=True, changefunc=self.toggled_flags)

        self.main_worker = MainWorker(self)

    def new_default_display(self, option_index):
        full_option_name, option_short_name = self.default_display_options[option_index]
        self.main_worker.default_display(option_short_name)

    def toggled_irating(self, new_state):
        self.main_worker.enable_irating(bool(new_state))

    def toggled_license(self, new_state):
        self.main_worker.enable_license(bool(new_state))

    def toggled_flags(self, new_state):
        self.main_worker.enable_flags(bool(new_state))

    def toggled_laps(self, new_state):
        self.main_worker.enable_laps(bool(new_state))

    def toggled_bestlap(self, new_state):
        self.main_worker.enable_bestlap(bool(new_state))

    def toggled_position(self, new_state):
        self.main_worker.enable_position(bool(new_state))

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

    def connected_to_iracing(self):

        self.toggled_irating(self.checkBox_IRating.isChecked())
        self.toggled_license(self.checkBox_License.isChecked())
        self.toggled_flags(self.checkBox_Flags.isChecked())
        self.toggled_laps(self.checkBox_Laps.isChecked())
        self.toggled_bestlap(self.checkBox_BestLap.isChecked())
        self.toggled_position(self.checkBox_Position.isChecked())
        self.new_default_display(self.comboBox_DefaultDisplay.currentIndex())

        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(0,150,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage(('STATUS: iRacing client detected.'))

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
                msg.setIconPixmap(QPixmap("ui/green_tick.png"))
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
        self.main_worker.deactivate()
        self.main_worker.wait()
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
    root.main_worker.start()
    ret = qapp.exec_()
    sys.exit(ret)