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
    pyqtSlot,
    pyqtSignal
)
from window import Window, Dialog
from pyirsdk import IRSDK


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

        self.dialog: Optional[MyDialog] = None

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

        """
        self.register_widget(self.lastLapLineEdit)
        self.register_widget(self.bestLapLineEdit)

        self.register_widget(self.start_hidden)
        self.register_widget(self.checkered)
        self.register_widget(self.white)
        self.register_widget(self.green)
        self.register_widget(self.yellow)
        self.register_widget(self.red)
        self.register_widget(self.blue)
        self.register_widget(self.debris)
        self.register_widget(self.crossed)
        self.register_widget(self.yellow_waving)
        self.register_widget(self.one_lap_to_green)
        self.register_widget(self.green_held)
        self.register_widget(self.ten_to_go)
        self.register_widget(self.five_to_go)
        self.register_widget(self.random_waving)
        self.register_widget(self.caution)
        self.register_widget(self.caution_waving)
        self.register_widget(self.black)
        self.register_widget(self.disqualify)
        self.register_widget(self.furled)
        """

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
            pass
        try:
            data["LicString"] = self.driver['LicString']
        except KeyError:
            pass
        try:
            data["LapBestLapTime"] = self.ir['LapBestLapTime']
        except KeyError:
            pass

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
        
        if self.custIDLineEdit.text is not f"{data['custid']}":
            self.custIDLineEdit.setText(f"{data['custid']}")
        if self.licenseLineEdit.text is not f"{data['LicString']}":
            self.licenseLineEdit.setText(f"{data['LicString']}")
        if self.bestLapLineEdit.text is not f"{data['LapBestLapTime']}":
            self.bestLapLineEdit.setText(f"{data['LapBestLapTime']}")
        if self.lastLapLineEdit.text is not f"{data['LastLapTime']}":
            self.lastLapLineEdit.setText(f"{data['LastLapTime']}")

        if not self.last_flags == self.ir['SessionFlags']:
            update_required = True
            print("Flag Change")
            print(f"Last: {self.last_flags}")
            print(f"Current: {self.ir['SessionFlags']}")

            if self.ir['SessionFlags'] & irsdk.Flags.start_hidden:
                print("Continuous green")
                self.start_hidden.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Green"})

            if self.ir['SessionFlags'] & irsdk.Flags.checkered:
                print("Checkered Flag")
                self.checkered.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Checkered"})

            if self.ir['SessionFlags'] & irsdk.Flags.white:
                print("White Flag")
                self.white.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "White"})

            if self.ir['SessionFlags'] & irsdk.Flags.green:
                print("Green flag")
                self.green.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Green"})

            if self.ir['SessionFlags'] & irsdk.Flags.yellow:
                print("Yellow flag")
                self.yellow.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Yellow"})

            if self.ir['SessionFlags'] & irsdk.Flags.red:
                print("Red flag")
                self.red.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Red"})

            if self.ir['SessionFlags'] & irsdk.Flags.blue:
                print("Blue flag")
                self.blue.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Blue"})

            if self.ir['SessionFlags'] & irsdk.Flags.debris:
                print("Debris flag")
                self.debris.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Debris"})

            if self.ir['SessionFlags'] & irsdk.Flags.crossed:
                print("Crossed flags")
                self.crossed.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Crossed"})

            if self.ir['SessionFlags'] & irsdk.Flags.yellow_waving:
                print("Yellow waving flag")
                self.yellow_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Yellow waving"})

            if self.ir['SessionFlags'] & irsdk.Flags.one_lap_to_green:
                print("One lap to green")
                self.one_lap_to_green.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "1 to Green"})

            if self.ir['SessionFlags'] & irsdk.Flags.green_held:
                print("Green flag held")
                self.green_held.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Green held"})

            if self.ir['SessionFlags'] & irsdk.Flags.ten_to_go:
                print("Ten to go")
                self.ten_to_go.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "10 to go"})

            if self.ir['SessionFlags'] & irsdk.Flags.five_to_go:
                print("Five to go")
                self.five_to_go.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "5 to go"})

            if self.ir['SessionFlags'] & irsdk.Flags.random_waving:
                print("Random waving flag")
                self.random_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Random"})

            if self.ir['SessionFlags'] & irsdk.Flags.caution:
                print("Caution Flag")
                self.cauting.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Caution"})

            if self.ir['SessionFlags'] & irsdk.Flags.caution_waving:
                print("Caution waving Flag")
                self.caution_waving.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Caution waving"})

            if self.ir['SessionFlags'] & irsdk.Flags.black:
                print("Black Flag")
                self.black.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Black"})

            if self.ir['SessionFlags'] & irsdk.Flags.disqualify:
                print("DQ Flag")
                self.disqualify.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "DQ"})

            if self.ir['SessionFlags'] & irsdk.Flags.furled:
                print("Furled black Flag")
                self.furled.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Furled black"})

            if self.ir['SessionFlags'] & irsdk.Flags.repair:
                print("Meatball Flag")
                self.repair.setChecked(True)
                update_required = True
                json['model']['frames'].append({"icon": "i43085", "text": "Meatball"})
          
            self.last_flags = self.ir['SessionFlags']

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
        pprint(self.ir['LapBestLapTime'])
        self.timerMainCycle.start()

    def onDisconnection(self):
        self.ir_connected = False
        self.statusBar().setStyleSheet("QStatusBar{padding-left:8px;padding-bottom:2px;background:rgba(150,0,0,200);color:white;font-weight:bold;}")
        self.statusBar().showMessage('STATUS: Waiting for iRacing client...')
        self.timerMainCycle.stop()

    def send_notification(self, json):
        if self.lametric_ip and self.lametric_api_key:
            headers = {"Content-Type": "application/json; charset=utf-8"}
            basicAuthCredentials = ("dev", self.lametric_api_key)
            try:
                response = requests.post(
                    self.lametric_url,
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
            self.dialog = MyDialog()

        self.dialog.show(modal)

    def closeEvent(self, e):
        super().closeEvent(e)
        e.accept()
        QCoreApplication.exit()


class MyDialog(Dialog):
    def __init__(self):
        super(MyDialog, self).__init__("ui/SettingsDialog.ui")

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