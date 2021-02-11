#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pprint import pprint
from dataclasses import dataclass, field
import traceback
import requests
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


@dataclass
class Data(object):
    """ a generic object to collect up the data we need from the irsdk
    """

    name: str = None
    irating: int = None
    license_string: str = None
    license_letter: str = None
    safety_rating: float = None
    position: int = None
    laps: int = None
    laps_left: int = None
    last_laptime: float = None
    best_laptime: float = None
    fuel_per_lap: float = None
    fuel_left: float = None
    time_left: float = None
    flags: int = None


@dataclass
class Icons(object):
    """ a generic object to pass around information regarding the icons
    """

    ir: str = 'i43085'
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
    purple: str = 'i43599'

@dataclass
class State(object):
    """ a generic object to pass around information regarding the current state
    """

    ir_connected: bool = False
    last_car_setup_tick: int = -1
    race_started: bool = False


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

        self.register_widget(self.checkBox_Name, default=True)
        self.register_widget(self.checkBox_IRating, default=True)
        self.register_widget(self.checkBox_License, default=True)
        self.register_widget(self.checkBox_Position, default=True)
        self.register_widget(self.checkBox_Laps, default=True)
        self.register_widget(self.checkBox_LapsLeft, default=True)
        self.register_widget(self.lineEdit_Name)
        self.register_widget(self.lineEdit_IRating)
        self.register_widget(self.lineEdit_License)
        self.register_widget(self.lineEdit_Position)
        self.register_widget(self.lineEdit_Laps)
        self.register_widget(self.lineEdit_LapsLeft)

        self.register_widget(self.checkBox_LastLap, default=True)
        self.register_widget(self.checkBox_BestLap, default=True)
        self.register_widget(self.checkBox_FuelPerLap, default=True)
        self.register_widget(self.checkBox_FuelLeft, default=True)
        self.register_widget(self.checkBox_TimeLeft, default=True)
        self.register_widget(self.checkBox_Flags, default=True)
        self.register_widget(self.lineEdit_LastLap)
        self.register_widget(self.lineEdit_BestLap)
        self.register_widget(self.lineEdit_FuelPerLap)
        self.register_widget(self.lineEdit_FuelLeft)
        self.register_widget(self.lineEdit_TimeLeft)

        self.ir = IRSDK()
        self.state = State()
        self.data = Data()

        self.ir_connected = False
        self.car_in_world = False
        self.last_irating = None
        self.last_flags = None

        self.threadpool = QThreadPool()

        self.timerConnectionMonitor = QTimer()
        self.timerConnectionMonitor.setInterval(1000)
        self.timerConnectionMonitor.timeout.connect(self.irsdkConnectionMonitor)
        self.timerConnectionMonitor.start()

        self.timerMainCycle = QTimer()
        self.timerMainCycle.setInterval(1)
        self.timerMainCycle.timeout.connect(self.main_cycle)

        s = QSettings()
        #s.clear()
        #pprint(s.allKeys())

    # here we check if we are connected to iracing
    # so we can retrieve some data
    def irsdk_connection_check(self):
        if self.state.ir_connected and not (self.ir.is_initialized and self.ir.is_connected):
            self.state.ir_connected = False
            # don't forget to reset your State variables
            self.state.last_car_setup_tick = -1
            # we are shutting down ir library (clearing all internal variables)
            self.ir.shutdown()
            return False
        elif not self.state.ir_connected and self.ir.startup(silent=True) and self.ir.is_initialized and self.ir.is_connected:
            self.state.ir_connected = True
            return True
        elif self.ir.is_initialized and self.ir.is_connected:
            return True
             
    def irsdk_connection_controller(self, now_connected):
        if now_connected and not self.ir_connected:
            self.onConnection()
        elif not now_connected and self.ir_connected:
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
        self.update_data('irating', int(self.driver['IRating']))
        self.update_data('license_string', self.driver['LicString'])
        license_letter, safety_rating = self.driver['LicString'].split(' ')
        self.update_data('license_letter', license_letter)
        self.update_data('safety_rating', float(safety_rating))
        self.update_data('best_laptime', float(self.ir['LapBestLapTime']))
        self.update_data('last_laptime', float(self.ir['LapLastLapTime']))
        self.update_data('flags', int(self.ir['SessionFlags']))
        self.ir.unfreeze_var_buffer_latest()

    def process_data(self):
        update_required = False
        json = {
            "priority": "info",
            "icon_type":"none",
            "model": {
                "cycles": 0,
                "frames": []
            }
        }

        if self.lineEdit_Name.text is not self.data.name:
            self.lineEdit_Name.setText(self.data.name)

        if self.last_irating != self.data.irating:
            self.last_irating = self.data.irating
            self.lineEdit_IRating.setText(f"{self.data.irating:,}")
            if self.checkBox_IRating.isChecked():
                update_required = True
                json["model"]["frames"].append({"icon": "i43085", "text": f"{self.data.irating:,}"})

        if self.lineEdit_License.text is not self.data.license_string:
            self.lineEdit_License.setText(self.data.license_string)
            if self.checkBox_License.isChecked():
                icon = Icons.ir
                if self.data.license_letter == 'R':
                    icon = Icons.license_letter_r
                elif self.data.license_letter == 'D':
                    icon = Icons.license_letter_d
                elif self.data.license_letter == 'C':
                    icon = Icons.license_letter_c
                elif self.data.license_letter == 'B':
                    icon = Icons.license_letter_b
                elif self.data.license_letter == 'A':
                    icon = Icons.license_letter_a
                elif self.data.license_letter == 'P':
                    icon = Icons.license_letter_p

                update_required = True
                json["model"]["frames"].append({"icon": icon, "text": f"{self.data.safety_rating}"})

        if self.lineEdit_BestLap.text is not f"{self.data.best_laptime}":
            # if there's a new best lap, it should over ride ir and license... so we make a new json
            self.lineEdit_BestLap.setText(f"{self.data.best_laptime}")
            update_required = True
            json = {
                "priority": "info",
                "icon_type":"none",
                "model": {
                    "cycles": 0,
                    "frames": [{"icon": Icons.purple, "text": f"{self.data.best_laptime}"}]
                }
            }

        if self.lineEdit_LastLap.text is not f"{self.data.last_laptime}":
            self.lineEdit_LastLap.setText(f"{self.data.last_laptime}")

        if not self.last_flags == self.data.flags and self.checkBox_Flags.isChecked():
            # if there's a flag, it should over ride anything else that is trying to be displayed... so we empty the json
            json = {
                "priority": "info",
                "icon_type":"none",
                "model": {
                    "cycles": 0,
                    "frames": []
                }
            }
            update_required = True

            if self.data.flags & Flags.start_hidden and not self.state.race_started:
                self.state.race_started = True
                print("Race start")
                update_required = True
                json['model']['frames'].append({"icon": Icons.start_hidden, "text": "Start"})

            if self.data.flags & Flags.checkered:
                print("Checkered Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.checkered, "text": "Finish"})

            if self.data.flags & Flags.white:
                print("White Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.white, "text": "White"})

            if self.data.flags & Flags.green:
                print("Green flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.green, "text": "Green"})

            if self.data.flags & Flags.yellow:
                print("Yellow flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.yellow, "text": "Yellow"})

            if self.data.flags & Flags.red:
                print("Red flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.red, "text": "Red"})

            if self.data.flags & Flags.blue:
                print("Blue flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.blue, "text": "Blue"})

            if self.data.flags & Flags.debris:
                print("Debris flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.debris, "text": "Debris"})

            if self.data.flags & Flags.crossed:
                print("Crossed flags")
                update_required = True
                json['model']['frames'].append({"icon": Icons.crossed, "text": "Crossed"})

            if self.data.flags & Flags.yellow_waving:
                print("Yellow waving flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.yellow_waving, "text": "Yellow"})

            if self.data.flags & Flags.one_lap_to_green:
                print("One lap to green")
                update_required = True
                json['model']['frames'].append({"icon": Icons.one_lap_to_green, "text": "1 to Green"})

            if self.data.flags & Flags.green_held:
                print("Green flag held")
                update_required = True
                json['model']['frames'].append({"icon": Icons.green_held, "text": "Green"})

            if self.data.flags & Flags.ten_to_go:
                print("Ten to go")
                update_required = True
                json['model']['frames'].append({"icon": Icons.ten_to_go, "text": "10 to go"})

            if self.data.flags & Flags.five_to_go:
                print("Five to go")
                update_required = True
                json['model']['frames'].append({"icon": Icons.five_to_go, "text": "5 to go"})

            if self.data.flags & Flags.random_waving:
                print("Random waving flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.random_waving, "text": "Random"})

            if self.data.flags & Flags.caution:
                print("Caution Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.caution, "text": "Caution"})

            if self.data.flags & Flags.caution_waving:
                print("Caution waving Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.caution_waving, "text": "Caution"})

            if self.data.flags & Flags.black:
                print("Black Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.black, "text": "Black"})

            if self.data.flags & Flags.disqualify:
                print("DQ Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.disqualify, "text": "DQ"})

            if self.data.flags & Flags.furled:
                print("Furled black Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.furled, "text": "Warning"})

            if self.data.flags & Flags.repair:
                print("Meatball Flag")
                update_required = True
                json['model']['frames'].append({"icon": Icons.repair, "text": "Damage"})
          
            self.last_flags = self.data.flags

        if update_required:
            self.send_notification(json)

        

    def main_cycle(self):
        main_cycle_worker = Worker(self.data_collection_cycle)
        main_cycle_worker.signals.result.connect(self.process_data)
        
        self.threadpool.start(main_cycle_worker)

    def onConnection(self):
        self.ir_connected = True
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(0,150,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage(('STATUS: iRacing client detected.'))

        for dvr in self.ir['DriverInfo']['Drivers']:
            if dvr['CarIdx'] == self.ir['DriverInfo']['DriverCarIdx']:
                self.driver = dvr
                break

        pprint(self.driver)
        self.timerMainCycle.start()

    def onDisconnection(self):
        self.ir_connected = False
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')
        self.timerMainCycle.stop()

    def send_notification(self, json):
        s = QSettings()

        pprint(json)

        try:
            self.lametric_ip = s.value('lametric-iracing/Settings/laMetricTimeIPLineEdit')
        except:
            self.lametric_ip = None
        try:
            self.lametric_api_key = s.value('lametric-iracing/Settings/aPIKeyLineEdit')
        except:
            self.lametric_api_key = None

        pprint([self.lametric_ip, self.lametric_api_key])
        
        if self.lametric_ip and self.lametric_api_key:
            lametric_url = f"http://{self.lametric_ip}:8080/api/v2/device/notifications"
            headers = {"Content-Type": "application/json; charset=utf-8"}
            basicAuthCredentials = ("dev", self.lametric_api_key)
            try:
                response = requests.post(
                    lametric_url,
                    headers=headers,
                    auth=basicAuthCredentials,
                    json=json,
                    timeout=1,
                )
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
        json = {
            "priority": "info",
            "icon_type": "none",
            "model": {
                "cycles": 0,
                "frames": []
            }
        }
        json['model']['frames'].append({"icon": Icons.start_hidden, "text": "Start"})
        json['model']['frames'].append({"icon": Icons.checkered, "text": "Finish"})
        json['model']['frames'].append({"icon": Icons.white, "text": "White"})
        json['model']['frames'].append({"icon": Icons.green, "text": "Green"})
        json['model']['frames'].append({"icon": Icons.yellow, "text": "Yellow"})
        json['model']['frames'].append({"icon": Icons.red, "text": "Red"})
        json['model']['frames'].append({"icon": Icons.blue, "text": "Blue"})
        json['model']['frames'].append({"icon": Icons.black, "text": "Black"})
        json['model']['frames'].append({"icon": Icons.disqualify, "text": "DQ"})
        json['model']['frames'].append({"icon": Icons.repair, "text": "Damage"})
        json['model']['frames'].append({"icon": Icons.furled, "text": "Warn"})
        json['model']['frames'].append({"icon": Icons.debris, "text": "Debris"})
    
        self.send_notification(json)

    def closeEvent(self, e):
        super().closeEvent(e)
        self.ir.shutdown()
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