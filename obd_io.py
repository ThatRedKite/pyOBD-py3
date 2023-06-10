#!/usr/bin/env python
###########################################################################
# odb_io.py
# 
# Copyright 2004 Donour Sizemore (donour@uchicago.edu)
# Copyright 2009 Secons Ltd. (www.obdtester.com)
#
# This file is part of pyOBD.
#
# pyOBD is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# pyOBD is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyOBD; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
###########################################################################

import serial
import time
from math import ceil
import wx  # due to debugEvent messaging

from debugEvent import *
from dtc import *


# __________________________________________________________________________

class OBDPort:
    """ OBDPort abstracts all communication with OBD-II device."""

    def __init__(self, portnum, _notify_window, SERTIMEOUT, RECONNATTEMPTS):
        """Initializes port by resetting device and gettings supported PIDs. """
        # These should really be set by the user.
        baud = 9600
        databits = 8
        par = serial.PARITY_NONE  # parity
        sb = 1  # stop bits
        to = SERTIMEOUT
        self.ELMver = "Unknown"
        self.State = 1  # state SERIAL is 1 connected, 0 disconnected (connection failed)

        self._notify_window = _notify_window
        wx.PostEvent(self._notify_window, DebugEvent([1, "Opening interface (serial port)"]))

        #try:
        self.port = serial.Serial(portnum, baud, parity=par, stopbits=sb, bytesize=databits, timeout=to)

        #except serial.SerialException:
        #    self.State = 0
        #    return

        wx.PostEvent(self._notify_window, DebugEvent([1, "Interface successfully " + self.port.portstr + " opened"]))
        wx.PostEvent(self._notify_window, DebugEvent([1, "Connecting to ECU..."]))

        count = 0
        while 1:  # until error is returned try to connect
            try:
                self.send_command(b"atz")  # initialize
            except serial.SerialException:
                self.State = 0
                return

            self.ELMver = self.get_result()
            wx.PostEvent(self._notify_window, DebugEvent([2, "atz response:" + self.ELMver]))
            self.send_command("ate0")  # echo off
            wx.PostEvent(self._notify_window, DebugEvent([2, "ate0 response:" + self.get_result()]))

            self.send_command("ATSP0")
            wx.PostEvent(self._notify_window, DebugEvent([2, "ATSP0 response:" + self.get_result()]))

            self.send_command("0100")
            ready = self.get_result()
            wx.PostEvent(self._notify_window, DebugEvent([2, "0100 response1:" + ready]))

            if ready != "BUS ERROR":
                wx.PostEvent(self._notify_window, DebugEvent([2, "0100 response2:" + ready]))
                return

            else:
                # ready=ready[-5:] #Expecting error message: BUSINIT:.ERROR (parse last 5 chars)
                wx.PostEvent(self._notify_window, DebugEvent([2, "Connection attempt failed:" + ready]))
                time.sleep(5)
                if count == RECONNATTEMPTS:
                    self.close()
                    self.State = 0
                    return

                wx.PostEvent(self._notify_window, DebugEvent([2, "Connection attempt:" + str(count)]))
                count = count + 1

    def close(self):
        """ Resets device and closes all associated filehandles"""

        if self.port and self.State == 1:
            self.send_command("atz")
            self.port.close()

        self.port = None
        self.ELMver = "Unknown"

    def send_command(self, cmd):
        """Internal use only: not a public interface"""
        if self.port:
            self.port.flushOutput()
            self.port.flushInput()
            for c in cmd:
                self.port.write(bytes(cmd))
            self.port.write(b"\r\n")
            wx.PostEvent(self._notify_window, DebugEvent([3, "Send command:" + str(cmd)]))

    def interpret_result(self, code):
        """Internal use only: not a public interface"""
        # Code will be the string returned from the device.
        # It should look something like this:
        # '41 11 0 0\r\r'

        # 9 seems to be the length of the shortest valid response
        if len(code) < 7:
            raise ValueError("Invalid Response")

        # get the first thing returned, echo should be off
        code = code.split("\r")
        code = code[0]

        # remove whitespace
        code = code.replace(" ", "")

        # cables can behave differently
        if code[:6] == "NODATA":  # there is no such sensor
            return "NODATA"

        # first 4 characters are code from ELM
        code = code[4:]
        return code

    def get_result(self):
        """Internal use only: not a public interface"""
        time.sleep(0.1)
        if self.port:
            buffer = ""
            while True:
                c = self.port.read(1)
                if c == '\r' and len(buffer) > 0:
                    break
                else:
                    if buffer != "" or c != ">":  # if something is in buffer, add everything
                        buffer = buffer + str(c)
            wx.PostEvent(self._notify_window, DebugEvent([3, "Get result:" + buffer]))
            return buffer
        else:
            wx.PostEvent(self._notify_window, DebugEvent([3, "NO self.port!" + ""]))
        return None

    # get sensor value from command
    def get_sensor_value(self, sensor):
        """Internal use only: not a public interface"""
        cmd = sensor.cmd
        self.send_command(cmd)
        data = self.get_result()

        if data:
            data = self.interpret_result(data)
            if data != "NODATA":
                data = sensor.value(data)
        else:
            return "NORESPONSE"
        return data

    # return string of sensor name and value from sensor index
    def sensor(self, sensor_index):
        """Returns 3-tuple of given sensors. 3-tuple consists of
         (Sensor Name (string), Sensor Value (string), Sensor Unit (string) ) """
        sensor = obd_sensors.SENSORS[sensor_index]
        r = self.get_sensor_value(sensor)
        return (sensor.name, r, sensor.unit)

    def sensor_names(self):
        """Internal use only: not a public interface"""
        names = []
        for s in obd_sensors.SENSORS:
            names.append(s.name)
        return names

    def get_tests_MIL(self):
        statusText = ["Unsupported", "Supported - Completed", "Unsupported", "Supported - Incompleted"]

        statusRes = self.sensor(1)[1]  # GET values
        statusTrans = []  # translate values to text

        statusTrans.append(str(statusRes[0]))  # DTCs

        if statusRes[1] == 0:  # MIL
            statusTrans.append("Off")
        else:
            statusTrans.append("On")

        for i in range(2, len(statusRes)):  # Tests
            statusTrans.append(statusText[int(statusRes[int(i)])])

        return statusTrans

    #
    # fixme: j1979 specifies that the program should poll until the number
    # of returned DTCs matches the number indicated by a call to PID 01
    #
    def log(self, sensor_index, filename):
        file = open(filename, "w")
        start_time = time.time()
        if file:
            data = self.sensor(sensor_index)
            file.write("%s     \t%s(%s)\n" % ("Time", data[0].strip(), data[2]))
            while 1:
                now = time.time()
                data = self.sensor(sensor_index)
                line = "%.6f,\t%s\n" % (now - start_time, data[1])
                file.write(line)
                file.flush()
