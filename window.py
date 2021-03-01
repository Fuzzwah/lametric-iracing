# -*- coding: utf-8 -*-

from enum import Enum, auto
from sys import argv
from pathlib import Path
from collections import OrderedDict
from datetime import datetime, date
from typing import Set, Type, Dict, Any
from PySide6.QtCore import QSettings, QSize, Qt, QDateTime, QByteArray, QMetaObject
from PySide6.QtWidgets import QMainWindow, QDialog, QDateTimeEdit, QCheckBox, QLineEdit, QComboBox, QDockWidget, QWidget
from PySide6.QtUiTools import QUiLoader


class UiLoader(QUiLoader):
    """
    Subclass :class:`~PySide.QtUiTools.QUiLoader` to create the user interface
    in a base instance.
    Unlike :class:`~PySide.QtUiTools.QUiLoader` itself this class does not
    create a new instance of the top-level widget, but creates the user
    interface in an existing instance of the top-level class.
    This mimics the behaviour of :func:`PyQt4.uic.loadUi`.
    """

    def __init__(self, baseinstance, customWidgets=None):
        """
        Create a loader for the given ``baseinstance``.
        The user interface is created in ``baseinstance``, which must be an
        instance of the top-level class in the user interface to load, or a
        subclass thereof.
        ``customWidgets`` is a dictionary mapping from class name to class object
        for widgets that you've promoted in the Qt Designer interface. Usually,
        this should be done by calling registerCustomWidget on the QUiLoader, but
        with PySide 1.1.2 on Ubuntu 12.04 x86_64 this causes a segfault.
        ``parent`` is the parent object of this loader.
        """

        QUiLoader.__init__(self, baseinstance)
        self.baseinstance = baseinstance
        self.customWidgets = customWidgets

    def createWidget(self, class_name, parent=None, name=''):
        """
        Function that is called for each widget defined in ui file,
        overridden here to populate baseinstance instead.
        """

        if parent is None and self.baseinstance:
            # supposed to create the top-level widget, return the base instance
            # instead
            return self.baseinstance

        else:
            if class_name in self.availableWidgets():
                # create a new widget for child widgets
                widget = QUiLoader.createWidget(self, class_name, parent, name)

            else:
                # if not in the list of availableWidgets, must be a custom widget
                # this will raise KeyError if the user has not supplied the
                # relevant class_name in the dictionary, or TypeError, if
                # customWidgets is None
                try:
                    widget = self.customWidgets[class_name](parent)

                except (TypeError, KeyError) as e:
                    raise Exception('No custom widget ' + class_name + ' found in customWidgets param of UiLoader __init__.')

            if self.baseinstance:
                # set an attribute for the new child widget on the base
                # instance, just like PyQt4.uic.loadUi does.
                setattr(self.baseinstance, name, widget)

                # this outputs the various widget names, e.g.
                # sampleGraphicsView, dockWidget, samplesTableView etc.
                #print(name)

            return widget


def loadUi(uifile, baseinstance=None, customWidgets=None,
           workingDirectory=None):
    """
    Dynamically load a user interface from the given ``uifile``.
    ``uifile`` is a string containing a file name of the UI file to load.
    If ``baseinstance`` is ``None``, the a new instance of the top-level widget
    will be created.  Otherwise, the user interface is created within the given
    ``baseinstance``.  In this case ``baseinstance`` must be an instance of the
    top-level widget class in the UI file to load, or a subclass thereof.  In
    other words, if you've created a ``QMainWindow`` interface in the designer,
    ``baseinstance`` must be a ``QMainWindow`` or a subclass thereof, too.  You
    cannot load a ``QMainWindow`` UI file with a plain
    :class:`~PySide.QtGui.QWidget` as ``baseinstance``.
    ``customWidgets`` is a dictionary mapping from class name to class object
    for widgets that you've promoted in the Qt Designer interface. Usually,
    this should be done by calling registerCustomWidget on the QUiLoader, but
    with PySide 1.1.2 on Ubuntu 12.04 x86_64 this causes a segfault.
    :method:`~PySide.QtCore.QMetaObject.connectSlotsByName()` is called on the
    created user interface, so you can implemented your slots according to its
    conventions in your widget class.
    Return ``baseinstance``, if ``baseinstance`` is not ``None``.  Otherwise
    return the newly created instance of the user interface.
    """

    loader = UiLoader(baseinstance, customWidgets)

    if workingDirectory is not None:
        loader.setWorkingDirectory(workingDirectory)

    widget = loader.load(uifile)
    QMetaObject.connectSlotsByName(widget)
    return widget


class PathRelativity(Enum):
    MAINPY = auto()  # Relative to __file__ of __main__. (Folder where your main script locates)
    CWD = auto()  # Current working directory


if argv[0]:
    _MAINPYDIR = Path(argv[0]).resolve().absolute().parent
else:
    _MAINPYDIR = Path.cwd()


def _abspath(path, relativity: PathRelativity) -> Path:
    if not isinstance(path, Path):
        path = Path(path)

    if relativity is PathRelativity.MAINPY:
        return (_MAINPYDIR / path).resolve()

    elif relativity is PathRelativity.CWD:
        return (Path.cwd() / path).resolve()

    else:
        raise TypeError("Unknown PathRelativity given:" + str(relativity))


# QDateTimeEdit
def dte(widget: QDateTimeEdit):
    def set_value(value):
        if value is None:
            widget.setDate(datetime.now())
        else:
            if type(value) is str:
                widget.setDate(datetime.fromisoformat(value))
            if isinstance(value, (date, QDialog)):
                widget.setDate(value)
            if isinstance(value, (datetime, QDateTime)):
                widget.setDateTime(value)

    def get_value() -> QDateTime:
        return widget.dateTime()

    def get_value_str():
        return get_value().toPyDate().isoformat()

    widget.set_value_ = set_value
    widget.get_value_ = get_value
    widget.get_value_str_ = get_value_str

    return widget.dateTimeChanged  # TODO args?


# QCheckBox
def chb(widget: QCheckBox):
    def set_value(value):
        if value is None:
            widget.setChecked(False)
        else:
            if type(value) is bool:
                widget.setChecked(value)
            if type(value) is int:
                widget.setChecked(bool(value))
            if type(value) is str:
                widget.setChecked(value.lower() not in ("false", "0", ""))

    def get_value() -> bool:
        return widget.isChecked()

    def get_value_str():
        return str(get_value())

    widget.set_value_ = set_value
    widget.get_value_ = get_value
    widget.get_value_str_ = get_value_str

    return widget.stateChanged  # TODO args?


# QComboBox
def cb(widget: QComboBox):
    def set_value(value):
        index = widget.findData(value, flags=Qt.MatchExactly)  # "Excatly" matches also int vs. str. Good!
        widget.setCurrentIndex(index)  # Not found: -1

    def get_value():
        return widget.currentData()

    def get_value_str() -> str:
        return str(get_value())

    widget.set_value_ = set_value
    widget.get_value_ = get_value
    widget.get_value_str_ = get_value_str

    return widget.currentIndexChanged  # int index


# QLineEdit
def qle(widget: QLineEdit):
    def set_value(value):
        if value is None:
            widget.setText("")
        else:
            if type(value) is str:
                widget.setText(value)
            else:
                widget.setText(str(value))

    def get_value() -> str:
        return widget.text()

    def get_value_str() -> str:
        return get_value()

    widget.set_value_ = set_value
    widget.get_value_ = get_value
    widget.get_value_str_ = get_value_str

    return widget.returnPressed  # TODO args?


# QDockWidget
def dw(widget: QDockWidget):
    # Add problematic dock position attributes
    widget.dockloc_ = 1
    widget.visible_ = True

    dwdata = OrderedDict(
        isfloating=bool,
        docklocation=int,
        posx=int,
        posy=int,
        width=int,
        height=int,
        visible=bool,
    )

    def get_datalist() -> tuple:
        pos = widget.pos()
        return (
            widget.isFloating(),
            widget.dockloc_,
            pos.x(),
            pos.y(),
            widget.width(),
            widget.height(),
            widget.isVisible()
        )

    def set_value(value):
        # parse string
        if type(value) is str:
            strvalues = value.split(",")
            d = dict(zip(dwdata.keys(), (t(v) for t, v in zip(dwdata.values(), strvalues))))
            set_value(d)

        if type(value) is dict:
            window: QMainWindow = widget.parent()

            widget.visible_ = value.get("visible", True)

            if widget.visible_:
                if "isfloating" in value:
                    isfloating = value["isfloating"]

                    if isfloating:
                        window.removeDockWidget(widget)
                        widget.setFloating(True)

                    else:
                        if "docklocation" in value:
                            # No direct method available
                            loc = value["docklocation"]
                            window.removeDockWidget(widget)
                            widget.setFloating(False)
                            if loc:
                                window.addDockWidget(loc, widget)

                if "width" in value and "height" in value:
                    # For initial size when docked
                    widget.widget().sizeHint = lambda: QSize(value["width"], value["height"])

                    if "posx" in value and "posy" in value:
                        # For floating state
                        widget.setGeometry(value["posx"], value["posy"], value["width"], value["height"])

                widget.show()
            else:
                window.removeDockWidget(widget)
                widget.hide()

    def get_value() -> dict:
        d = dict(zip(dwdata.keys(), get_datalist()))
        return d

    def get_value_str():
        pos = widget.pos()
        s = "{0},{1},{2},{3},{4},{5},{6}".format(str(int(widget.isFloating())), str(widget.dockloc_),
                                                 str(pos.x()), str(pos.y()), str(widget.width()),
                                                 str(widget.height()), str(widget.isVisible()))
        return s

    widget.set_value_ = set_value
    widget.get_value_ = get_value
    widget.get_value_str_ = get_value_str

    def changed_area(w, area):
        # Always track last dock position. Ignore floating.
        if area:
            w.dockloc_ = area

    widget.dockLocationChanged.connect(lambda newarea: changed_area(widget, newarea))

    return None


class SaveWindow(QWidget):
    # Supported Widgets ###################
    __handler: Dict[Type[QWidget], Any] = {
        QDateTimeEdit: dte,
        QCheckBox: chb,
        QLineEdit: qle,
        QComboBox: cb,
        QDockWidget: dw,
    }
    #######################################

    def __init__(self):
        # QWidget.__init__(self)
        self.__positioned = False
        self.__widgets_data: Set[QWidget] = set()
        self.__widgets_size: Set[QWidget] = set()

    def settings(self) -> QSettings:
        s = QSettings()
        s.beginGroup("lametric-iracing/" + self.objectName())
        return s

    def settings_save(self):
        s = self.settings()
        s.setValue("geometry", self.saveGeometry())
        s.endGroup()
        s.sync()

    def settings_restore(self):
        s = self.settings()

        geo = s.value("geometry", None)
        if isinstance(geo, QByteArray):
            self.restoreGeometry(geo)

        s.endGroup()

    def register_widget(self, widget: QWidget, default=None, changefunc=None, individualsettings=None):
        widget.__default_value = default
        widget.__individual_settings = individualsettings
        widget.__func = changefunc
        widget.__set_data = True
        self.__widgets_data.add(widget)

    def register_size(self, widget):
        widget.__set_size = True
        self.__widgets_size.add(widget)

    def __widgets_setup(self):
        s = self.settings()

        for widget in self.__widgets_data:
            wtype: Type[QWidget] = type(widget)
            if wtype in self.__handler:
                signal = self.__handler[wtype](widget)

                # Set saved value
                try:
                    name = widget.objectName()
                    defaultvalue = widget.__default_value
                    widget.set_value_(s.value(name, defaultvalue))

                except Exception as e:
                    print(e)

            else:
                print("SaveWindow.register_widget(" + str(wtype) + ") not implemented.")

        for widget in self.__widgets_size:  # type: QWidget
            size = s.value(widget.objectName() + "_size", None)
            if size:
                widget.resize(size)

    def __widgets_savedata(self):
        s = self.settings()
        for widget in self.__widgets_data:
            s.setValue(widget.objectName(), widget.get_value_())

        for widget in self.__widgets_size:
            s.setValue(widget.objectName() + "_size", widget.size())

    def show(self):
        if not self.__positioned:
            self.settings_restore()
            self.__widgets_setup()
            self.__positioned = True

    def closeEvent(self, e):
        self.settings_save()  # Window's data
        self.__widgets_savedata()  # Widget's data
        super().closeEvent(e)


class Window(QMainWindow, SaveWindow):
    def __init__(self, uifile: str, relativity: PathRelativity = PathRelativity.MAINPY):
        realfile = _abspath(uifile, relativity)
        if not realfile.is_file():
            raise ValueError("ui file does not exists: " + str(realfile))

        QMainWindow.__init__(self, flags=Qt.Window)
        SaveWindow.__init__(self)

        loadUi(str(realfile), self)

    def show(self):
        SaveWindow.show(self)
        QMainWindow.show(self)
        QMainWindow.setFocus(self)
        QMainWindow.activateWindow(self)

    def closeEvent(self, e):
        # Would work without this override.
        # But does not with QDialog.
        # So better explicit call on both classes.

        QMainWindow.closeEvent(self, e)
        SaveWindow.closeEvent(self, e)


class Dialog(QDialog, SaveWindow):
    def __init__(self, uifile: str, relativity: PathRelativity = PathRelativity.MAINPY):
        realfile = _abspath(uifile, relativity)
        if not realfile.is_file():
            raise ValueError("ui file does not exists: " + str(realfile))

        QDialog.__init__(self, flags=Qt.Dialog)
        SaveWindow.__init__(self)

        loadUi(str(realfile), self)

        self.s = QSettings()

    def show(self, modal: bool = False):
        SaveWindow.show(self)

        if modal:
            QDialog.setWindowModality(self, Qt.ApplicationModal)
            QDialog.show(self)
            QDialog.exec_(self)  # Modal
        else:
            QDialog.show(self)
            QDialog.setFocus(self)
            QDialog.activateWindow(self)

        self.buttonBox.accepted.connect(self.save)

    def save(self):
        self.close()

    def closeEvent(self, e):
        # Without explicit delegation it does not call SaveWindow.closeEvent.
        QDialog.closeEvent(self, e)
        SaveWindow.closeEvent(self, e)