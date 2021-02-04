#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from typing import Optional
from PyQt5.QtCore import QCoreApplication, pyqtSlot, Qt
from PyQt5.QtWidgets import QApplication, QComboBox
from window import Window, Dialog


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
        self.register_widget(self.lastLapLineEdit)
        self.register_widget(self.bestLapLineEdit)

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