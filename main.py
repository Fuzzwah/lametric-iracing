#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pprint import pprint
import requests
import traceback
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
from window import Window, Settings
from pyirsdk import (
    IRSDK,
    Flags
)


class State:
    ir_connected = False
    last_car_setup_tick = -1

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
            data["UserID"] = f"{self.driver['UserID']:,}"
        except KeyError:
            data["UserID"] = ""
        try:
            data["UserName"] = self.driver['UserName']
        except KeyError:
            data["UserName"] = ""
        try:
            data["LastLapTime"] = self.ir['LastLapTime']
        except KeyError:
            data["LastLapTime"] = ""
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
        if self.lastLapLineEdit.text is not f"{data['LastLapTime']}":
            self.lastLapLineEdit.setText(f"{data['LastLapTime']}")

        if not self.last_flags == data['SessionFlags']:
            update_required = True
            print("Flag Change")
            print(f"Last: {self.last_flags}")
            print(f"Current: {data['SessionFlags']}")

            if data['SessionFlags'] & Flags.start_hidden:
                print("Continuous green")
                self.start_hidden.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43453", "text": "Green"})

            if data['SessionFlags'] & Flags.checkered:
                print("Checkered Flag")
                self.checkered.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43451", "text": "Checkered"})

            if data['SessionFlags'] & Flags.white:
                print("White Flag")
                self.white.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43448", "text": "White"})

            if data['SessionFlags'] & Flags.green:
                print("Green flag")
                self.green.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43453", "text": "Green"})

            if data['SessionFlags'] & Flags.yellow:
                print("Yellow flag")
                self.yellow.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43439", "text": "Yellow"})

            if data['SessionFlags'] & Flags.red:
                print("Red flag")
                self.red.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43446", "text": "Red"})

            if data['SessionFlags'] & Flags.blue:
                print("Blue flag")
                self.blue.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43449", "text": "Blue"})

            if data['SessionFlags'] & Flags.debris:
                print("Debris flag")
                self.debris.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43456", "text": "Debris"})

            if data['SessionFlags'] & Flags.crossed:
                print("Crossed flags")
                self.crossed.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Crossed"})

            if data['SessionFlags'] & Flags.yellow_waving:
                print("Yellow waving flag")
                self.yellow_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Yellow waving"})

            if data['SessionFlags'] & Flags.one_lap_to_green:
                print("One lap to green")
                self.one_lap_to_green.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "1 to Green"})

            if data['SessionFlags'] & Flags.green_held:
                print("Green flag held")
                self.green_held.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43457", "text": "Green held"})

            if data['SessionFlags'] & Flags.ten_to_go:
                print("Ten to go")
                self.ten_to_go.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "10 to go"})

            if data['SessionFlags'] & Flags.five_to_go:
                print("Five to go")
                self.five_to_go.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "5 to go"})

            if data['SessionFlags'] & Flags.random_waving:
                print("Random waving flag")
                self.random_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43458", "text": "Random"})

            if data['SessionFlags'] & Flags.caution:
                print("Caution Flag")
                self.cauting.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43447", "text": "Caution"})

            if data['SessionFlags'] & Flags.caution_waving:
                print("Caution waving Flag")
                self.caution_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43447", "text": "Caution waving"})

            if data['SessionFlags'] & Flags.black:
                print("Black Flag")
                self.black.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43450", "text": "Black"})

            if data['SessionFlags'] & Flags.disqualify:
                print("DQ Flag")
                self.disqualify.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43454", "text": "DQ"})

            if data['SessionFlags'] & Flags.furled:
                print("Furled black Flag")
                self.furled.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43455", "text": "Furled black"})

            if data['SessionFlags'] & Flags.repair:
                print("Meatball Flag")
                self.repair.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43452", "text": "Meatball"})
          
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
    def on_pushButton_clicked(self):
        self.open_dialog()

    @pyqtSlot()
    def on_pushButtonModal_clicked(self):
        self.open_dialog(True)

    def open_dialog(self, modal: bool = False):
        if self.dialog is None:
            self.dialog = SettingsDialog()

        self.dialog.show(modal)

    def closeEvent(self, e):
        super().closeEvent(e)
        self.ir.shutdown()
        e.accept()
        QCoreApplication.exit()


class SettingsDialog(Settings):
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
    root.show()
    ret = qapp.exec_()
    sys.exit(ret)