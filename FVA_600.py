# -*- coding: utf-8 -*-
import ctypes
import struct
from typing import Union
from .FVA_600_utilities import CheckDeviceError, DWORD, FT_HANDLE, USBListDevices, USBOpen,\
USBSetTimeouts, USBSetLatency, USBSetBaudRate, USBSetDataCharacteristics, USBSetFlowControl, USBWrite,\
USBPurge, USBRead, USBClose, crc16, unpack_first, pyint_to_byte, DeviceDescriptor, CurrentState,\
DeviceStatus, DeviceError

def list_devices():
    '''Lists all compatible devices, returns a list of indices for USNB communication initialization'''
    NB_DEVICES = DWORD()
    USBListDevices(ctypes.byref(NB_DEVICES),None,0x80000000)
    list_serial_numbers = []
    for i in range(NB_DEVICES.value):
        try:
            INDEX = ctypes.c_void_p(i)
            
            #id string read, check if starts with FVA
            ID = ctypes.create_string_buffer(64)
            USBListDevices(INDEX,ID,0x40000002)
            if ID.value.decode('ansi').startswith("FVA"):
                list_serial_numbers+=[i]
        except:
            pass
    
    if len(list_serial_numbers) == 0 :
        raise SystemError("No compatible device found !")

    return list_serial_numbers

class FVA600:
    '''This driver is not thread-safe, do not use with concurrent access (only one instance in a single thread per device)
       By default opens the first FVA device seen, the index of the device to open can be selected at object initialization'''
    
    def __init__(self,index_to_open = 0):
        #Device list construction
        self.is_closed = True
        list_num = list_devices()
        
        #Communication initialization
        self.HANDLE = FT_HANDLE()
        USBOpen(list_num[index_to_open],ctypes.byref(self.HANDLE))
        self.is_closed = False
        #Timeouts config : 2s for R/W
        USBSetTimeouts(self.HANDLE, 2000, 2000)
        #Latency config : 100ms
        USBSetLatency(self.HANDLE, 100)
        #Baudrate config : 115200
        USBSetBaudRate(self.HANDLE, 115200)
        #Data characteristics config : word length 8 bits, 1 stop bit, no parity
        USBSetDataCharacteristics(self.HANDLE, 8, 0, 0)
        #Flow control config : no control
        USBSetFlowControl(self.HANDLE, 0, 0, 0)
        
        self.set_remote(True)
        
        #Try twice to build the device descriptor to acount for errors in the transmission
        try:
            self.device_descriptor = self.populate_device_descr()
        except:
            try:
                self.device_descriptor = self.populate_device_descr()
            except:
                self.close()
                raise SystemError("Device properties read : failure")
        
    #Interface configuration for use with context manager (with)
    def __enter__(self):
        return self
    
    def __exit__(self,*args):
        self.close()
    
    def query_device(self, command: Union[bytearray,bytes], retry : int = 10) -> bytes :
        '''Send raw command to device 
        The command must be written in little-endian
        The command will be retried retry times (default : 10) in case of transmission errors'''
        
        if self.is_closed:
            raise SystemError("The communication with the device is closed")
        
        #Sending buffer creation
        temp_buf = struct.pack(f'<H{len(command)}s', len(command), command)
        final_buf = struct.pack(f'<{len(temp_buf)}sH', temp_buf, crc16(temp_buf))
        
        for i in range(retry):
            try:
                #Data writing
                LEN_WRITTEN = DWORD()
                final_len = len(final_buf)
                USBPurge(self.HANDLE, 3)
                USBWrite(self.HANDLE, final_buf, final_len, ctypes.byref(LEN_WRITTEN))
                if LEN_WRITTEN.value != final_len:
                    raise Exception("USB communication timeout")
                
                #Result reception : reading of the response length
                BUFFER1 = ctypes.create_string_buffer(3)
                USBRead(self.HANDLE, BUFFER1, 3, ctypes.byref(LEN_WRITTEN))
                if LEN_WRITTEN.value != 3:
                    raise Exception("USB communication timeout")
                error, length = struct.unpack("<BH",BUFFER1)
                CheckDeviceError(error)
                break
            except DeviceError as err :
                #Retry in case of error : 99% of the time this happens because of a communication cut at the wrong moment
                last_error = err
                continue
        else:
            #If the for loop was left without using the break, this means we encountered an error retyr times : raise the error in this case
            raise last_error
        
        BUFFER2 = ctypes.create_string_buffer(length)
        USBRead(self.HANDLE, BUFFER2, length, ctypes.byref(LEN_WRITTEN))
        if LEN_WRITTEN.value != length:
            raise Exception("USB communication timeout")
        
        USBPurge(self.HANDLE, 3)
        
        return bytes(BUFFER2) 
    
    def close(self):
        """Closes communication. If already closed, does nothing"""
        if not self.is_closed:
            self.set_remote(False)
            USBClose(self.HANDLE)
            self.is_closed = True
    
    def __del__(self):
        """Closes communication even if destroyed by garbage collection"""
        self.close()
    
    @property
    def status(self) -> DeviceStatus:
        """Current status of the device."""
        if self.is_closed:
            return DeviceStatus.DISCONNECTED
        else:
            #Magic value for status query : 188
            ret = self.query_device(struct.pack('<B',188))
            flag1, flag2, flag3 = unpack_first('<BBB', ret)
            if flag2 == 1:
                return DeviceStatus.CORRECTING
            elif flag1 == 1:
                return DeviceStatus.SETTLING
            elif flag3 == 1:
                return DeviceStatus.DEFECTIVE
            else:
                return DeviceStatus.IDLE
    
    @property
    def current_state(self) -> CurrentState:
        """Current state of the device : wavelength, attenuation"""
        #Magic value for current state query : 183
        ret = self.query_device(struct.pack('<B', 183))
        wav, att, low_att, high_att = unpack_first('<ffff',ret)
        return CurrentState(wav,(round(low_att,2),round(high_att,2)), round(att,2))
    
    @property
    def wavelength(self) -> float:
        """Returns wavelength in nanometers"""
        return self.current_state.wavelength
    
    @wavelength.setter
    def wavelength(self, value : int):
        wlRange = self.device_descriptor.wavelengthRange
        if value < wlRange[0]:
            raise ValueError(f"The given wavelength {value} is below the minimum {wlRange[0]}")
        if value > wlRange[1]:
            raise ValueError(f"the given wavelength {value} is above the maximum {wlRange[1]}")
        
        #Magic value for wavelength setting : 177 
        self.query_device(struct.pack('<Bf',177,value))
        
        #Wait for device to end the change
        while self.status == DeviceStatus.SETTLING :
            continue
     
    @property
    def attenuation(self) -> float:
        """Returns attenuation as a positive dB value"""
        return self.current_state.attenuation
   
    @attenuation.setter
    def attenuation(self, value : float):
        attRange = self.current_state.attRange
        value = round(value,2)
        if value < attRange[0]:
            raise ValueError(self,f"Attenuation {value} is smaller than minimum {attRange[0]}")
        if value > attRange[1]:
            raise ValueError(self,f"Attenuation {value} is bigger than maximum {attRange[1]}")
        
        #Magic value for attenuation setting : 179 
        self.query_device(struct.pack('<Bf',179,value))
        
        #Wait for device to end the change. Can take up to 10s
        while self.status == DeviceStatus.SETTLING :
            continue
    
    def populate_device_descr(self):
        '''Reading of all the device fixed properties'''
        #Id : magic number 0
        ret = self.query_device(pyint_to_byte(0))
        ident = ret.partition(b'\x00')[0].decode('ansi')
        manuf, model, ser, *_ = ident.split(',')
        manuf = manuf.strip(' ')
        model = model.strip(' ')
        ser = ser.strip(' ')
        
        #Firmware : magic number 58
        ret = self.query_device(pyint_to_byte(58))
        firm = ret.partition(b'\x00')[0].decode('ansi')
        
        #Specs : magic number 187
        ret = self.query_device(pyint_to_byte(187))
        low_wl, high_wl = unpack_first('<ff',ret)
        fiber_type, _, ret  = ret[struct.calcsize('<fffBfB'):].partition(b'\x00')
        fiber_type = fiber_type.decode('ansi')
        attLin, attRep = unpack_first('<ff',ret)
        
        #Wavelenghts list
        #Number of wavelengths : magic number 165
        #Get wavelength from index : magic number 167
        ret = self.query_device(pyint_to_byte(165))
        nb = unpack_first('<B', ret)[0]
        wl_list = []
        for i in range(nb):
            ret = self.query_device(struct.pack('<BB', 167, i))
            wl_list += unpack_first('<f', ret)
        
        #Attenuation steps 
        #Number of step : magic number 161
        #Get specific step from list : magic number 163
        ret = self.query_device(pyint_to_byte(161))
        nb = unpack_first('<B', ret)[0]
        att_steps = []
        for i in range(nb):
            ret = self.query_device(struct.pack('<BB', 163, i))
            att_steps += unpack_first('<f', ret)
        
        return DeviceDescriptor(manuf, model, ser, firm, fiber_type, (low_wl,high_wl), attLin, attRep ,wl_list, att_steps)

    def set_remote(self,remote : bool):
        '''Switches the device between remote or local control'''
        #Magic number : 112
        if remote:
            self.query_device(struct.pack('<BB',112,1))
        else:
            self.query_device(struct.pack('<BB',112,0))
    
    def do_zero_device(self, wait_for_end : bool = True):
        '''Resets the zero of the mechanical attenuation.
        Call only when the device is idle.
        wait_for_end controls whether the function waits for operation complete'''
        stat = self.status
        if stat != DeviceStatus.IDLE :
            raise DeviceError(f"The device is not idle : status {stat.name}")
        
        #There can be errors while asking to do the zero
        #One possible error is that the device reads correctly the request to do the zero, but an error occurs in the ack
        #In this case, retrying inside query_device will always raise a (legitimate) error, as the device is not idle anymore
        #So we have to implement a retry outside the call to query_device
        for i in range(10):
            try:
                #Magic number : 186
                self.query_device(struct.pack('<B', 186),retry = 0)
                break
            except Exception as err:
                if self.status == DeviceStatus.CORRECTING:
                    break
                current_error = err
        else:
            raise current_error
        
        if wait_for_end:
            #Wait for the zero to finish
            while self.status == DeviceStatus.CORRECTING :
                continue
    