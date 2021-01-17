# iRacing displays for LaMetic Time smart clock

## Overview

This is a Windows application that collects various pieces of data from the iRacing API and sends them via push notifcations to be displayed on a LaMetic Time device.

## Technical details

The GUI for the application is created using Qt5, the information is collected from iRacing using the `pyirsdk` library. The data is formatted in the json required by the LaMetric device, and received by a companion app that I have released on the LaMetric app store named `iRacing Info Display`.

## Requirements

You will need to purchase, install, and configure the `iRacing Info Display` app from the LaMetic store.