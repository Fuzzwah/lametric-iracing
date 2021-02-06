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
        super().__init__("ui/MainWindow_new.ui")

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

        self.register_widget(self.driverNameLineEdit)
        self.register_widget(self.custIDLineEdit)
        self.register_widget(self.iRatingLineEdit)
        self.register_widget(self.licenseLineEdit)

        self.ir = IRSDK()
        self.state = State()

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
        pprint(s.allKeys())

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

    def data_collection_cycle(self):
        self.ir.freeze_var_buffer_latest()
        data = {}
        try:
            data["IRating"] = f"{self.driver['IRating']:,}"
        except KeyError:
            data["IRating"] = ""
        try:
            data["LicString"] = self.driver['LicString']
        except KeyError:
            data["LicString"] = ""
        try:
            data["LapBestLapTime"] = self.ir['LapBestLapTime']
        except KeyError:
            data["LapBestLapTime"] = ""
        try:
            data["UserID"] = f"{self.driver['UserID']}"
        except KeyError:
            data["UserID"] = ""
        try:
            data["UserName"] = self.driver['UserName']
        except KeyError:
            data["UserName"] = ""
        try:
            data["LapLastLapTime"] = self.ir['LapLastLapTime']
        except KeyError:
            data["LapLastLapTime"] = ""
        try:
            data['SessionFlags'] = self.ir['SessionFlags']
        except KeyError:
            data['SessionFlags'] = 0

        return data

    def process_data(self, data):
        update_required = False
        json = {
            "priority": "info",
            "icon_type":"none",
            "model": {
                "cycles": 0,
                "frames": []
            }
        }
        if self.last_irating != f"{data['IRating']}":
            update_required = True
            self.last_irating = f"{data['IRating']}"
            self.iRatingLineEdit.setText(f"{data['IRating']}")
            json["model"]["frames"].append({"icon": "i43085", "text": data['IRating']})
            json["model"]["frames"].append({"icon": "i43085", "text": data["LicString"]})
        
        if self.custIDLineEdit.text is not f"{data['UserID']}":
            self.custIDLineEdit.setText(f"{data['UserID']}")
        if self.driverNameLineEdit.text is not f"{data['UserName']}":
            self.driverNameLineEdit.setText(f"{data['UserName']}")            
        if self.licenseLineEdit.text is not f"{data['LicString']}":
            self.licenseLineEdit.setText(f"{data['LicString']}")
        if self.bestLapLineEdit.text is not f"{data['LapBestLapTime']}":
            self.bestLapLineEdit.setText(f"{data['LapBestLapTime']}")
        if self.lastLapLineEdit.text is not f"{data['LapLastLapTime']}":
            self.lastLapLineEdit.setText(f"{data['LapLastLapTime']}")

        if not self.last_flags == data['SessionFlags']:
            update_required = True

            if data['SessionFlags'] & Flags.start_hidden:
                if not self.state.race_started:
                    self.state.race_started = True
                    print("Race start")
                    self.start_hidden.setChecked(True)
                    update_required = True
                    json['model']['frames'].append({"icon": Icons.start_hidden, "text": "Start"})

            if data['SessionFlags'] & Flags.checkered:
                print("Checkered Flag")
                self.checkered.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.checkered, "text": "Finish"})

            if data['SessionFlags'] & Flags.white:
                print("White Flag")
                self.white.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.white, "text": "White"})

            if data['SessionFlags'] & Flags.green:
                print("Green flag")
                self.green.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.green, "text": "Green"})

            if data['SessionFlags'] & Flags.yellow:
                print("Yellow flag")
                self.yellow.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.yellow, "text": "Yellow"})

            if data['SessionFlags'] & Flags.red:
                print("Red flag")
                self.red.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.red, "text": "Red"})

            if data['SessionFlags'] & Flags.blue:
                print("Blue flag")
                self.blue.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.blue, "text": "Blue"})

            if data['SessionFlags'] & Flags.debris:
                print("Debris flag")
                self.debris.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.debris, "text": "Debris"})

            if data['SessionFlags'] & Flags.crossed:
                print("Crossed flags")
                self.crossed.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.crossed, "text": "Crossed"})

            if data['SessionFlags'] & Flags.yellow_waving:
                print("Yellow waving flag")
                self.yellow_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.yellow_waving, "text": "Yellow"})

            if data['SessionFlags'] & Flags.one_lap_to_green:
                print("One lap to green")
                self.one_lap_to_green.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.one_lap_to_green, "text": "1 to Green"})

            if data['SessionFlags'] & Flags.green_held:
                print("Green flag held")
                self.green_held.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.green_held, "text": "Green"})

            if data['SessionFlags'] & Flags.ten_to_go:
                print("Ten to go")
                self.ten_to_go.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.ten_to_go, "text": "10 to go"})

            if data['SessionFlags'] & Flags.five_to_go:
                print("Five to go")
                self.five_to_go.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.five_to_go, "text": "5 to go"})

            if data['SessionFlags'] & Flags.random_waving:
                print("Random waving flag")
                self.random_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.random_waving, "text": "Random"})

            if data['SessionFlags'] & Flags.caution:
                print("Caution Flag")
                self.cauting.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.caution, "text": "Caution"})

            if data['SessionFlags'] & Flags.caution_waving:
                print("Caution waving Flag")
                self.caution_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.caution_waving, "text": "Caution"})

            if data['SessionFlags'] & Flags.black:
                print("Black Flag")
                self.black.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.black, "text": "Black"})

            if data['SessionFlags'] & Flags.disqualify:
                print("DQ Flag")
                self.disqualify.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.disqualify, "text": "DQ"})

            if data['SessionFlags'] & Flags.furled:
                print("Furled black Flag")
                self.furled.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.furled, "text": "Furled black"})

            if data['SessionFlags'] & Flags.repair:
                print("Meatball Flag")
                self.repair.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": Icons.repair, "text": "Damage"})
          
            self.last_flags = data['SessionFlags']

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