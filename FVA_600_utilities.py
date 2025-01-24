# -*- coding: utf-8 -*-
import ctypes
from ctypes import wintypes
import struct
from enum import IntEnum,auto,Enum
from typing import NamedTuple
from crcmod.predefined import mkCrcFun
import platform

##################################################
###### Utilities for device error checking #######
##################################################

class DeviceError(Exception):
    pass

class DeviceErrorTypes(IntEnum):
    OK = 0
    OSCILLATOR_FAULT = 4
    PROTOCOL_ERROR = 5
    UNDEFINED_COMMAND = 6
    BAD_COMMAND_LEVEL = 7
    PARAMETER_ERROR = 8
    TOO_LONG_RESPONSE = 9
    INVALID_CRC = 10
    INTERNAL_TIME_OUT = 0xF
    CONFIGURATION_ERROR = 34
    INCONSISTENT_CALIBRATION = 36
    ATTENUATOR_NOT_CALIBRATED = 37
    SUSPICIOUS_CALIBRATION = 38
    PROTECTED_EEPROM = 40
    EEPROM_VERSION_ERROR = 41
    WRITE_EEPROM_ERROR = 42
    EPPROM_NOT_RESPONDING = 43
    CAL_EEPROM_NOT_PRESENT = 44
    DATA_EEPROM_NOT_PRESENT = 45
    CAL_EEPROM_NOT_CONFIG = 46
    DATA_EEPROM_NOT_CONFIG = 47
    DATA_RECORDER_PROBLEM = 48
    READ_EEPROM_ERROR = 49
    TEMPERATURE_NOT_PRESENT = 79
    MOTOR_OPTO_SWITCH = 81
    MOTOR_SETTLING = 82
    MOTOR_CORRECTING = 83
    MOTOR_FIRST_HOME = 85
    MOTOR_POSITION = 90
    MOTOR_MALFUNCTION = 92

def CheckDeviceError(value):
    try:
        value = DeviceErrorTypes(value)
    except ValueError:
        raise DeviceError(f"Unknown error : {value}")
    if value != DeviceErrorTypes.OK :
        raise DeviceError(value.name)

##################################################
#### Utilities for device error checking End  ####
##################################################

##################################################
############   USB driver import    ##############
##################################################

if platform.system() == "Windows":
    try:
        usb_lib = ctypes.WinDLL("FTD2XX")
    except FileNotFoundError:
        raise FileNotFoundError("USB drive not found. Did you install it ?")
else:
    #TODO : Import the driver in other OSes
    raise NotImplementedError("The USB driver communication has only been tested on Windows")
DWORD = wintypes.DWORD
FT_HANDLE = ctypes.c_void_p
UCHAR = ctypes.c_ubyte

class USBCommError(Exception):
    pass

class USBStatus(IntEnum):
	OK = 0
	INVALID_HANDLE = 1
	DEVICE_NOT_FOUND = auto()
	DEVICE_NOT_OPENED = auto()
	IO_ERROR = auto()
	INSUFFICIENT_RESOURCES = auto()
	INVALID_PARAMETER = auto()
	INVALID_BAUD_RATE = auto()
	DEVICE_NOT_OPENED_FOR_ERASE = auto()
	DEVICE_NOT_OPENED_FOR_WRITE = auto()
	FAILED_TO_WRITE_DEVICE = auto()
	EEPROM_READ_FAILED = auto()
	EEPROM_WRITE_FAILED = auto()
	EEPROM_ERASE_FAILED = auto()
	EEPROM_NOT_PRESENT = auto()
	EEPROM_NOT_PROGRAMMED = auto()
	INVALID_ARGS = auto()
	NOT_SUPPORTED = auto()
	OTHER_ERROR = auto()

def Check_FT(status,*args):
    stat = USBStatus(status)
    if stat != USBStatus.OK:
        raise USBCommError(stat.name)
        
def construct_import(func, proto):
    func.argtypes = proto
    func.restype = DWORD
    func.errcheck = Check_FT
    return func
        
#Functions imported from USB driver D2XX
#Reference : https://ftdichip.com/wp-content/uploads/2020/08/D2XX_Programmers_GuideFT_000071.pdf

#prototype = (void* arg1, void* arg2, DWORD flags)
USBListDevices = construct_import(usb_lib.FT_ListDevices, [ctypes.c_void_p, ctypes.c_void_p, DWORD])

#prototype = (int index, FT_HANDLE* p_handle)
USBOpen = construct_import(usb_lib.FT_Open, [ctypes.c_int, ctypes.POINTER(FT_HANDLE)])

#prototype = (FT_HANDLE handle, DWORD read_timeout, DWORD write_timeout)
USBSetTimeouts = construct_import(usb_lib.FT_SetTimeouts, [FT_HANDLE, DWORD, DWORD])

#prototype = (FT_HANDLE handle, UCHAR timer)
USBSetLatency = construct_import(usb_lib.FT_SetLatencyTimer, [FT_HANDLE, UCHAR])

#prototype = (FT_HANDLE handle, DWORD baudRate)
USBSetBaudRate = construct_import(usb_lib.FT_SetBaudRate, [FT_HANDLE, DWORD])

#prototype = (FT_HANDLE handle, UCHAR wordLength, UCHAR stopBits, UCHAR parity)
USBSetDataCharacteristics = construct_import(usb_lib.FT_SetDataCharacteristics, [FT_HANDLE, UCHAR, UCHAR, UCHAR])

#prototype = (FT_HANDLE handle, u_short flowControl, UCHAR Xon, UCHAR Xoff)
USBSetFlowControl = construct_import(usb_lib.FT_SetFlowControl, [FT_HANDLE, ctypes.c_ushort, UCHAR, UCHAR])

#prototype = (FT_HANDLE handle, void* data_to_write, DWORD len_to_write, DWORD* nb_bytes_written )
USBWrite = construct_import(usb_lib.FT_Write,[FT_HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD)])

#prototype = (FT_HANDLE handle, DWORD purgeFlags)
USBPurge = construct_import(usb_lib.FT_Purge, [FT_HANDLE, DWORD])

#prototype = (FT_HANDLE handle, void* buffer, DWORD len, DWORD* nb_bytes_read)
USBRead = construct_import(usb_lib.FT_Read, [FT_HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD)])

#prototype = (FT_HANDLE handle)
USBClose = construct_import(usb_lib.FT_Close, [FT_HANDLE])

##################################################
##########   USB driver import End   #############
##################################################

##################################################
#########  USB commnication utilities   ##########
##################################################

crc16 = mkCrcFun('modbus')

def unpack_first(fmt, buff):
    '''struct.unpack, mais en prenant que la partie utilisée du buffer'''
    return struct.unpack(fmt, buff[:struct.calcsize(fmt)])

pyint_to_byte = struct.Struct('<B').pack

##################################################
#######  USB commnication utilities end   ########
##################################################

##################################################
#######   Miscellaneous data structures   ########
##################################################

class DeviceDescriptor(NamedTuple):
    manufacturer : str
    model : str
    serial : str 
    firmware : str
    fiberType : str
    wavelengthRange : tuple
    attenuationLin : float
    attenuationRep : float
    wavelengthsList : tuple
    attStepList : tuple
    
class CurrentState(NamedTuple):
    wavelength : float
    attRange : tuple
    attenuation : float
    
class DeviceStatus(Enum):
    DISCONNECTED = auto()
    DEFECTIVE = auto()
    IDLE = auto()
    SETTLING = auto()
    CORRECTING = auto()
    
##################################################
######  Miscellaneous data structures End  #######
##################################################