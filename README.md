# iRacing displays for LaMetic Time smart clock

## Overview

This is a Windows application that collects various pieces of data from the iRacing API and sends them via push notifcations to be displayed on a LaMetic Time device.

## Technical Details

The GUI for the application is created using Qt5, the information is collected from iRacing using the `pyirsdk` library. The data is formatted in the json required by the LaMetric device, and sent to the clock using a HTTP POST call via `requests`.

## Minimum Viable Product

[x] Simple GUI
[x] iRacing API rigged up to collect iRating and License / Safety Rating info
[x] HTTP POST the iRating value to the device using hard coded address and key
