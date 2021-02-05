# iRacing displays for LaMetic Time smart clock

## Overview

This is an application to be run on a PC along side iRacing, that collects various pieces of data from the iRacing API and sends them via push notifcations to be displayed on a LaMetic Time device.


## Installation

While I do plan on creating a packaged installer, currently you'll need to follow the steps below to get the application up and running:

1. Install Python 3.8 (or later)
2. Install Git for Windows
3. Open a Git Bash console
4. Clone this repository

    ```
    git clone https://github.com/Fuzzwah/lametric-iracing.git 
    ```

5. Change into the newly created directory

    ```
    cd lametric-iracing
    ```

6. Install the virtualenv package

    ```
    py -m pip install --user virtualenv
    ```    

7. Create a new Python virtual environment

    ```
    py -m venv .env
    ```

8. Initialise the virtual environment

    ```
    .\.env\Scripts\activate
    ```

9. Install the required libraries

    ```
    py -m pip install -r requirements
    ```

10. Run the application

    ```
    py main.py
    ```

The first time you run the app, you'll be promoted to supply the IP address of your LaMetric Time device and the API Key. The IP address can be found in LaMetric Time app at `Settings -> Wi-Fi -> IP Address`. The API Key is displayed in the `Devices` tab over on the Developer Portal: https://developer.lametric.com/user/devices (Note: you'll need to create an account there where the username matches the user you setup in the LaMetric app on your phone).

Enter the IP and API Key and click the save button. On the main window there is a `Settings` button, if you need to update this info. Also on the main window is a `Send Test` button. Click this and confirm that the app is able to send notifications to your LaMetric clock.

If that works, fire up iRacing and be amazed at the information displayed on your clock!
## Technical Details

The GUI for the application is created using Qt5, the information is collected from iRacing using the `pyirsdk` library. The data is formatted in the json required by the LaMetric device, and sent to the clock using a HTTP POST call via `requests`.
