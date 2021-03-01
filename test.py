import sys
from time import sleep
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget


# Create a basic window with a layout and a button
class MainForm(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.setWindowTitle("My Form")
        self.layout = QVBoxLayout()
        self.start_button = QPushButton("start")
        self.start_button.clicked.connect(self.start_thread)
        self.layout.addWidget(self.start_button)
        self.stop_button = QPushButton("stop")
        self.stop_button.clicked.connect(self.stop_thread)
        self.layout.addWidget(self.stop_button)
        self.setLayout(self.layout)

        self.instanced_thread = WorkerThread(self)
        self.instanced_thread.started.connect(self.thread_started)
        self.instanced_thread.finished.connect(self.thread_finished)

    def thread_started(self):
        print("thread started")

    def thread_finished(self):
        print("thread finished")

    # Instantiate and start a new thread
    def start_thread(self):
        self.instanced_thread.start()

    def stop_thread(self):
        self.instanced_thread.deactivate()

    # Create the Slots that will receive signals
    @Slot(str)
    def update_str_field(self, message):
        print(message)

    @Slot(int)
    def update_int_field(self, value):
        print(value)


# Signals must inherit QObject
class MySignals(QObject):
    signal_str = Signal(str)
    signal_int = Signal(int)


# Create the Worker Thread
class WorkerThread(QThread):
    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        # Instantiate signals and connect signals to the slots
        self.signals = MySignals()
        self.signals.signal_str.connect(parent.update_str_field)
        self.signals.signal_int.connect(parent.update_int_field)
        self._active = False

    def deactivate(self):
        self._active = False

    def run(self):
        self._active = True
        # Do something on the worker thread
        while self._active:
            self.signals.signal_str.emit("string")
            for i in range(10):
                if self._active:
                    print(i)
                    sleep(0.2)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainForm()
    window.show()
    sys.exit(app.exec_())