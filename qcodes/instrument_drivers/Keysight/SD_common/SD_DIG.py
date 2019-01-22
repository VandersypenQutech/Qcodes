import numpy as np
import time, re, logging

from qcodes import VisaInstrument, validators as vals
from qcodes.utils.validators import Ints, Bool, Numbers, Enum
from qcodes import MultiParameter
from qcodes.instrument.channel import InstrumentChannel, ChannelList

from functools import partial

from .SD_Module import *

class line_trace(MultiParameter):
    def __init__(self, name, instrument, inst_name , raw=False):
        self.channels = []
        self.my_instrument = instrument
        self.mode = 0
        self.name = name

        super().__init__(name=inst_name,
                         names = (name, ),
                         shapes=((1,),),
                         labels=('Voltage',),
                         units=('V',),
                         # setpoint_names=('Time', )*len(channel),
                         # setpoint_labels=('Time', )*len(channel),
                         # setpoint_units=('s',)*len(channel),
                         docstring='Measured traces from digitizer')
        
    def set_channels(self, channels):
        """
            Enter channels you want to measure, either integer or list of channels

        """

        if type(self.channels) == int:
            # Todo make hard code for number of channels.
            if i < 1 or i > 4:
                raise "invalid channel number"
            self.channels = [self.channels]
        
        self.channels = channels

    def get(self):
        return self.get_rawish()

    def get_rawish(self):
        if self.channels == []:
            raise "please define channels by the meas_channel function."
        
        names = []
        self.channel_obj = []

        for i in self.channels:
            names.append(self.name+ '_ch{}'.format(i))
            self.channel_obj.append(self.my_instrument.channels[i-1])

        self.mode = self.my_instrument.data_mode()
        self.names = names
        self.shapes = self._mk_shapes(self.channel_obj, self.mode)
        self.labels = ('Voltage', )*len(self.channels)
        self.units = ('mV', )*len(self.channels)

        data = tuple()

        self.start_digitizers()
        for i in range(0,len(self.channels)):
            data += (self.get_data(self.channel_obj[i], self.shapes[i]), )

        return data

    @staticmethod
    def _mk_shapes(channel_data, mode):
        shapes = tuple()
        np_shape = []
        for i in channel_data:
            if mode == 0 :
                shapes += ((i.n_cycles(), i.points_per_cycle(), ), )
            elif mode == 1:
                shapes += ((i.points_per_cycle(),), )
            elif mode == 2:
                shapes += ((),)
            else: 
                raise "invalid data mode. This must be a number between 0 and 2. Checkout the source for the meaning."
        return shapes

    def get_data(self,channel_obj, shape):
        channel_data = np.zeros( [ channel_obj.n_cycles()*channel_obj.points_per_cycle()] )
        
        k = 0 
        # get data out of the buffer
        while k < len(channel_data):
            np_ready = self.my_instrument.SD_AIN.DAQcounterRead(channel_obj.channel)
            if np_ready == 0:
                continue
            data = self.my_instrument.SD_AIN.DAQread(channel_obj.channel, np_ready)
            np_ready  = len(data)
            channel_data[k: k+np_ready] = data
            k= k+ np_ready

        # correct amplitude,
        channel_data /= 32768 #convert bit to relative scale (-1/1)
        channel_data *= channel_obj.full_scale()*1000 #multiply with the relevant channel amplitude (standard in volt -> mV!)
        channel_data = channel_data.reshape([channel_obj.n_cycles(), channel_obj.points_per_cycle()])

        if self.mode == 0:
            return channel_data
        elif self.mode == 1:
            return np.average(channel_data, axis = 0)
        else:
            return np.average(channel_data)

    def start_digitizers(self):

        # start muplitple
        channel_mask = list('0000') # TODO make general version for n channels
        # make trigger mask
        for i in self.channels:
            channel_mask[-i] = '1'
        channel_mask = int(''.join(channel_mask), 2)

        self.my_instrument.daq_start_multiple(channel_mask)

        # trigger [TODO if needed]
        self.my_instrument.daq_trigger_multiple(channel_mask)

        # done!

class SD_DIG_channel(InstrumentChannel):
    def __init__(self, parent, name, channel):
        super().__init__(parent, name)
        self.channel =  channel
        # Store some standard settings.
        # For channelInputConfig
        self.__full_scale = 1   # By default, full scale = 1V
        self.__impedance = 0  # By default, Hi-z
        self.__coupling = 0  # By default, DC coupling
        # For channelPrescalerConfig
        self.__prescaler = 0  # By default, no prescaling
        # For channelTriggerConfig
        self.__trigger_mode = keysightSD1.SD_AIN_TriggerMode.RISING_EDGE 
        self.__trigger_threshold = 0  # By default, threshold at 0V
        # For DAQ config
        self.__points_per_cycle = 1
        self.__n_cycles = 1
        self.__DAQ_trigger_delay = 0
        self.__DAQ_trigger_mode = 0
        # For DAQ trigger Config
        self.__digital_trigger_mode = 0
        self.__digital_trigger_source = 0
        self.__analog_trigger_mask = 0
        # For DAQ trigger External Config
        self.__external_source = 0
        self.__trigger_behaviour = 0
        # For DAQ read
        self.__timeout = -1

        self.add_parameter(
            'full_scale',
            label='Full scale range for channel',
            # TODO: validator must be set after device opened
            # vals=Numbers(self.SD_AIN.channelMinFullScale(), self.SD_AIN.channelMaxFullScale())
            set_cmd=partial(self.set_full_scale, channel=channel),
            get_cmd=partial(self.get_full_scale, channel=channel),
            docstring='The full scale voltage for channel'
        )

        # For channelTriggerConfig
        self.add_parameter(
            'impedance',
            label='Impedance for channel',
            vals=Enum(0, 1),
            set_cmd=partial(self.set_impedance, channel=channel),
            get_cmd=partial(self.get_impedance, channel=channel),
            docstring='The input impedance of channel'
        )

        self.add_parameter(
            'coupling',
            label='Coupling for channel',
            vals=Enum(0, 1),
            set_cmd=partial(self.set_coupling, channel=channel),
            get_cmd=partial(self.get_coupling, channel=channel),
            docstring='The coupling of channel'
        )

        # For channelPrescalerConfig
        self.add_parameter(
            'prescaler',
            label='Prescaler for channel',
            vals=Ints(0, 4095),
            set_cmd=partial(self.set_prescaler, channel=channel),
            get_cmd=partial(self.get_prescaler, channel=channel),
            docstring='The sampling frequency prescaler for channel'
        )

        # For channelTriggerConfig
        self.add_parameter(
            'trigger_mode', label='Trigger mode for channel',
            vals=Enum(0, 1, 2, 3, 4, 5, 6, 7),
            set_cmd=partial(self.set_trigger_mode, channel=channel),
            docstring='The trigger mode for channel'
        )

        self.add_parameter(
            'trigger_threshold',
            label='Trigger threshold for channel',
            vals=Numbers(-3, 3),
            set_cmd=partial(self.set_trigger_threshold, channel=channel),
            docstring='The trigger threshold for channel'
        )

        # For DAQ config
        self.add_parameter(
            'points_per_cycle',
            label='Points per cycle for channel',
            vals=Ints(),
            set_cmd=partial(self.set_points_per_cycle, channel=channel),
            get_cmd=self.get_points_per_cycle,
            docstring='The number of points per cycle for DAQ'
        )

        self.add_parameter(
            'n_cycles',
            label='n cycles for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_n_cycles, channel=channel),
            get_cmd=self.get_n_cycles,
            docstring='The number of cycles to collect on DAQ'
        )

        self.add_parameter(
            'DAQ_trigger_delay',
            label='Trigger delay for for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_daq_trigger_delay, channel=channel),
            docstring='The trigger delay for DAQ'
        )

        self.add_parameter(
            'DAQ_trigger_mode',
            label='Trigger mode for for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_daq_trigger_mode, channel=channel),
            docstring='The trigger mode for DAQ'
        )

        # For DAQ trigger Config
        self.add_parameter(
            'digital_trigger_mode',
            label='Digital trigger mode for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_digital_trigger_mode, channel=channel),
            docstring='The digital trigger mode for DAQ'
        )

        self.add_parameter(
            'digital_trigger_source',
            label='Digital trigger source for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_digital_trigger_source, channel=channel),
            docstring='The digital trigger source for DAQ'
        )

        self.add_parameter(
            'analog_trigger_mask',
            label='Analog trigger mask for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_analog_trigger_mask, channel=channel),
            docstring='The analog trigger mask for DAQ'
        )

        # For DAQ trigger External Config
        self.add_parameter(
            'ext_trigger_source',
            label='External trigger source for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_ext_trigger_source, channel=channel),
            docstring='The trigger source for DAQ'
        )

        self.add_parameter(
            'ext_trigger_behaviour',
            label='External trigger behaviour for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_ext_trigger_behaviour, channel=channel),
            docstring='The trigger behaviour for DAQ'
        )

        self.add_parameter(
            'timeout',
            label='timeout for DAQ',
            vals=Ints(),
            set_cmd=partial(self.set_timeout, channel=channel),
            docstring='The read timeout for DAQ'
        )

    def set_channel_properties(self, V_range=1, impedance=1, coupling=0, prescaler=0):
        """
        sets quickly relevant channel properties.
        Args:
            V_range: amplitude range +- X Volts
            impedance: 0(HiZ), 1 (50 Ohm)
            coulping: 0 (DC), 1 (AC)
            prescalor: see manual, default 0
        """
        self.full_scale(V_range)
        self.impedance(impedance)
        self.coupling(coupling)
        self.prescaler(prescaler)

    def set_ext_digital_trigger(self, delay = 0, mode=3):
        """
        Set external trigger for current channel.
        Args:
            mode: 1(trig high), 2 (trig low), 3 (raising edge), 4 (falling edge)
        """
        # Make sure input port is enabled
        self.parent.SD_AIN.triggerIOconfig(1)

        self.DAQ_trigger_mode(2)
        self.DAQ_trigger_delay(delay)
        self.digital_trigger_source(0)
        self.digital_trigger_mode(mode)

    def get_prescaler(self, channel, verbose=False):
        """ Gets the channel prescaler value

        Args:
            channel (int)       : the input channel you are observing
        """
        value =self.parent.SD_AIN.channelPrescaler(channel)
        # Update internal parameter for consistency
        self.__prescaler = value
        value_name = 'get_prescaler'
        return result_parser(value, value_name, verbose)

    def set_prescaler(self, prescaler, channel, verbose=False):
        """ Sets the channel sampling frequency via the prescaler

        Args:
            channel (int)       : the input channel you are configuring
            prescaler (int)     : the prescaler value [0..4095]
        """
        self.__prescaler = prescaler
        value =self.parent.SD_AIN.channelPrescalerConfig(channel, prescaler)
        value_name = 'set_prescaler {}'.format(prescaler)
        return result_parser(value, value_name, verbose)

    # channelInputConfig
    # NOTE: When setting any of full_scale, coupling or impedance
    # the initial internal value is used as a placeholder, as all 3 arguments
    # are required at once to the Keysight library
    def get_full_scale(self, channel, verbose=False):
        """ Gets the channel full scale input voltage

        Args:
            channel(int)        : the input channel you are observing
        """
        value =self.parent.SD_AIN.channelFullScale(channel)
        # Update internal parameter for consistency
        self.__full_scale  = value
        value_name = 'get_full_scale'
        return result_parser(value, value_name, verbose)

    def set_full_scale(self, full_scale, channel, verbose=False):
        """ Sets the channel full scale input voltage

        Args:
            channel(int)        : the input channel you are configuring
            full_scale (float)  : the input full scale range in volts
        """
        self.__full_scale  = full_scale
        value =self.parent.SD_AIN.channelInputConfig(channel, self.__full_scale ,
                                               self.__impedance ,
                                               self.__coupling )
        value_name = 'set_full_scale {}'.format(full_scale)
        return result_parser(value, value_name, verbose)

    def get_impedance(self, channel, verbose=False):
        """ Gets the channel input impedance

        Args:
            channel (int)       : the input channel you are observing
        """
        value =self.parent.SD_AIN.channelImpedance(channel)
        # Update internal parameter for consistency
        self.__impedance  = value
        value_name = 'get_impedance'
        return result_parser(value, value_name, verbose)

    def set_impedance(self, impedance, channel, verbose=False):
        """ Sets the channel input impedance

        Args:
            channel (int)       : the input channel you are configuring
            impedance (int)     : the input impedance (0 = Hi-Z, 1 = 50 Ohm)
        """
        self.__impedance  = impedance
        value = self.parent.SD_AIN.channelInputConfig(channel, self.__full_scale ,
                                               self.__impedance ,
                                               self.__coupling )
        value_name = 'set_impedance {}'.format(impedance)
        return result_parser(value, value_name, verbose)

    def get_coupling(self, channel, verbose=False):
        """ Gets the channel coupling

        Args:
            channel (int)       : the input channel you are observing
        """
        value = self.parent.SD_AIN.channelCoupling(channel)
        # Update internal parameter for consistency
        self.__coupling  = value
        value_name = 'get_coupling'
        return result_parser(value, value_name, verbose)

    def set_coupling(self, coupling, channel, verbose=False):
        """ Sets the channel coupling

        Args:
            channel (int)       : the input channel you are configuring
            coupling (int)      : the channel coupling (0 = DC, 1 = AC)
        """
        self.__coupling  = coupling
        value = self.parent.SD_AIN.channelInputConfig(channel, self.__full_scale ,
                                               self.__impedance ,
                                               self.__coupling )
        value_name = 'set_coupling {}'.format(coupling)
        return result_parser(value, value_name, verbose)

    # channelTriggerConfig
    def set_trigger_mode(self, mode, channel, verbose=False):
        """ Sets the current trigger mode from those defined in SD_AIN_TriggerMode

        Args:
            channel (int)       : the input channel you are configuring
            mode (int)          : the trigger mode drawn from the class SD_AIN_TriggerMode
        """
        self.__trigger_mode  = mode
        value = self.parent.SD_AIN.channelTriggerConfig(channel, self.__analog_trigger_mask ,
                                                 self.__trigger_threshold )
        value_name = 'set_trigger_mode {}'.format(mode)
        return result_parser(value, value_name, verbose)

    def get_trigger_mode(self, channel):
        """ Returns the current trigger mode

        Args:
            channel (int)       : the input channel you are observing
        """
        return self.__trigger_mode 

    def set_trigger_threshold(self, threshold, channel, verbose=False):
        """ Sets the current trigger threshold, in the range of -3V and 3V

        Args:
            channel (int)       : the input channel you are configuring
            threshold (float)   : the value in volts for the trigger threshold
        """
        self.__trigger_threshold  = threshold
        value = self.parent.SD_AIN.channelTriggerConfig(channel, self.__analog_trigger_mask ,
                                                 self.__trigger_threshold )
        value_name = 'set_trigger_threshold {}'.format(threshold)
        return result_parser(value, value_name, verbose)

    def get_trigger_threshold(self, channel):
        """ Returns the current trigger threshold

        Args:
            channel (int)       : the input channel you are observing
        """
        return self.__trigger_threshold 

    # DAQConfig
    def set_points_per_cycle(self, n_points, channel, verbose=False):
        """ Sets the number of points to be collected per trigger

        Args:
            n_points (int)      : the number of points to collect per cycle
            channel (int)       : the input channel you are configuring
        """
        self.__points_per_cycle  = n_points
        value = self.parent.SD_AIN.DAQconfig(channel, self.__points_per_cycle ,
                                      self.__n_cycles ,
                                      self.__DAQ_trigger_delay ,
                                      self.__DAQ_trigger_mode )
        value_name = 'set_points_per_cycle {}'.format(n_points)
        return result_parser(value, value_name, verbose)

    def get_points_per_cycle(self):
        return self.__points_per_cycle

    def set_n_cycles(self, n_cycles, channel, verbose=False):
        """ Sets the number of trigger cycles to collect data for

        Args:
            channel (int)       : the input channel you are configuring
            n_cycles (int)      : the number of triggers to collect data from

        """
        self.__n_cycles  = n_cycles
        value = self.parent.SD_AIN.DAQconfig(channel, self.__points_per_cycle ,
                                      self.__n_cycles ,
                                      self.__DAQ_trigger_delay ,
                                      self.__DAQ_trigger_mode )
        value_name = 'set_n_cycles {}'.format(n_cycles)
        return result_parser(value, value_name, verbose)

    def get_n_cycles(self):
        return self.__n_cycles

    def set_daq_trigger_delay(self, delay, channel, verbose=False):
        """ Sets the trigger delay for the specified trigger source

        Args:
            channel (int)       : the input channel you are configuring
            delay   (int)       : the delay in unknown units
        """
        self.__DAQ_trigger_delay  = delay
        value = self.parent.SD_AIN.DAQconfig(channel, self.__points_per_cycle ,
                                      self.__n_cycles ,
                                      self.__DAQ_trigger_delay ,
                                      self.__DAQ_trigger_mode )
        value_name = 'set_DAQ_trigger_delay {}'.format(delay)
        return result_parser(value, value_name, verbose)

    def set_daq_trigger_mode(self, mode, channel, verbose=False):
        """ Sets the trigger mode when using an external trigger

        Args:
            channel (int)       : the input channel you are configuring
            mode  (int)         : the trigger mode you are using
        """
        self.__DAQ_trigger_mode  = mode
        value = self.parent.SD_AIN.DAQconfig(channel, self.__points_per_cycle ,
                                      self.__n_cycles ,
                                      self.__DAQ_trigger_delay ,
                                      self.__DAQ_trigger_mode )
        value_name = 'set_DAQ_trigger_mode {}'.format(mode)
        return result_parser(value, value_name, verbose)

    # DAQ trigger Config
    def set_digital_trigger_mode(self, mode, channel, verbose=False):
        """

        Args:
            channel (int)       : the input channel you are configuring
            mode  (int)         : the trigger mode you are using
        """
        self.__digital_trigger_mode  = mode
        value = self.parent.SD_AIN.DAQdigitalTriggerConfig(channel, self.__digital_trigger_source , self.__digital_trigger_mode)
        value_name = 'set_digital_trigger_mode {}'.format(mode)
        return result_parser(value, value_name, verbose)

    def set_digital_trigger_source(self, source, channel, verbose=False):
        """

        Args:
            channel (int)       : the input channel you are configuring
            source  (int)         : the trigger source you are using
        """
        self.__digital_trigger_source  = source
        value = self.parent.SD_AIN.DAQdigitalTriggerConfig(channel, self.__digital_trigger_source, self.__digital_trigger_mode )
        value_name = 'set_digital_trigger_source {}'.format(source)
        return result_parser(value, value_name, verbose)

    def set_analog_trigger_mask(self, mask, channel, verbose=False):
        """

        Args:
            channel (int)       : the input channel you are configuring
            mask  (int)         : the trigger mask you are using
        """
        self.__analog_trigger_mask  = mask
        value = self.parent.SD_AIN.DAQtriggerConfig(channel, self.__digital_trigger_mode ,
                                             self.__digital_trigger_source ,
                                             self.__analog_trigger_mask )
        value_name = 'set_analog_trigger_mask {}'.format(mask)
        return result_parser(value, value_name, verbose)

    # DAQ trigger External Config
    def set_ext_trigger_source(self, source, channel, verbose=False):
        """ Sets the trigger source

        Args:
            channel (int)       : the input channel you are configuring
            source  (int)       : the trigger source you are using
        """
        self.__external_source  = source
        value = self.parent.SD_AIN.DAQtriggerExternalConfig(channel, self.__external_source ,
                                                     self.__trigger_behaviour )
        value_name = 'set_ext_trigger_source {}'.format(source)
        return result_parser(value, value_name, verbose)

    def set_ext_trigger_behaviour(self, behaviour, channel, verbose=False):
        """ Sets the trigger source

        Args:
            channel (int)       : the input channel you are configuring
            behaviour  (int)    : the trigger behaviour you are using
        """
        self.__external_behaviour  = behaviour
        value = self.parent.SD_AIN.DAQtriggerExternalConfig(channel, self.__external_source ,
                                                     self.__trigger_behaviour )
        value_name = 'set_ext_trigger_behaviour {}'.format(behaviour)
        return result_parser(value, value_name, verbose)

    def set_timeout(self, timeout, channel):
        """ Sets the trigger source

        Args:
            channel (int)       : the input channel you are configuring
            timeout (int)       : the read timeout in ms for the specified DAQ
        """
        self.__timeout  = timeout

class SD_DIG(SD_Module):
    """
    This is the qcodes driver for a generic Signadyne Digitizer of the M32/33XX series.

    Status: beta

    This driver is written with the M3300A in mind.

    This driver makes use of the Python library provided by Keysight as part of the SD1 Software package (v.2.01.35).
    """

    def __init__(self, name, chassis, slot, channels, triggers, **kwargs):
        """ Initialises a generic Signadyne digitizer and its parameters

            Args:
                name (str)      : the name of the digitizer card
                channels (int)  : the number of input channels the specified card has
                triggers (int)  : the number of trigger inputs the specified card has
        """
        super().__init__(name, chassis, slot, **kwargs)

        # Create instance of keysight SD_AIN class
        self.SD_AIN = keysightSD1.SD_AIN()

        # store card-specifics
        self.n_channels = channels
        self.n_triggers = triggers

        self.__data_mode = 0
        # Open the device, using the specified chassis and slot number
        dig_name = self.SD_AIN.getProductNameBySlot(chassis, slot)
        if isinstance(dig_name, str):
            result_code = self.SD_AIN.openWithSlot(dig_name, chassis, slot)
            if result_code <= 0:
                raise Exception('Could not open SD_DIG '
                                'error code {}'.format(result_code))
        else:
            raise Exception('No SD_DIG found at '
                            'chassis {}, slot {}'.format(chassis, slot))

        self.add_parameter(
            'trigger_direction',
            label='Trigger direction for trigger port',
            vals=Enum(0, 1),
            set_cmd=self.SD_AIN.triggerIOconfig,
            docstring='The trigger direction for digitizer trigger port'
        )

        # for clockSetFrequency
        self.add_parameter(
            'sys_frequency',
            label='CLKsys frequency',
            vals=Ints(),
            set_cmd=self.SD_AIN.clockSetFrequency,
            get_cmd=self.SD_AIN.clockGetFrequency,
            docstring='The frequency of internal CLKsys in Hz'
        )

        # for clockGetSyncFrequency
        self.add_parameter(
            'sync_frequency',
            label='CLKsync frequency',
            vals=Ints(),
            get_cmd=self.SD_AIN.clockGetSyncFrequency,
            docstring='The frequency of internal CLKsync in Hz'
        )

        self.add_parameter('trigger_io',
                           label='trigger io',
                           get_cmd=self.get_trigger_io,
                           set_cmd=self.set_trigger_io,
                           docstring='The trigger input value, 0 (OFF) or 1 (ON)',
                           vals=Enum(0, 1))

        channels = ChannelList(self, "Channels", SD_DIG_channel, snapshotable=False)

        for channel_number in range(1, self.n_channels + 1):
            channel = SD_DIG_channel(self, "ch{}".format(channel_number), channel_number)
            channels.append(channel)

        channels.lock()
        self.add_submodule('channels', channels)

        self.add_parameter(
            'meas_channel',
            set_cmd = self.meas_channel,
            docstring='define the channels you want to measure in an array.'
            )

        self.add_parameter(
            'measure',
            inst_name = self.name,
            parameter_class=line_trace,
            raw =False
            )
        self.add_parameter(
            'data_mode',
            set_cmd=self.set_data_mode,
            docstring="MODES :\n\t0: Standard, return array with n points\n\t1: average cycles per channel\n\t2: total average of all measured data"
            )
    #
    # User functions
    #
    def meas_channel(self, channels):
        self.measure.set_channels(channels)

    def set_data_mode(self, mode):
        """
        MODES :
            0: Standard, return array with n points
            1: average cycles per channel
            2: total average of all measured data
        """
        self.__data_mode = mode

    def get_data_mode(self):
        return self.__data_mode

    def daq_read(self, daq, verbose=False):
        """ Read from the specified DAQ

        Args:
            daq (int)       : the input DAQ you are reading from

        Parameters:
            n_points
            timeout
        """
        value = self.SD_AIN.DAQread(daq, self.__n_points[daq], self.__timeout[daq])
        value_name = 'DAQ_read channel {}'.format(daq)
        return result_parser(value, value_name, verbose)

    def daq_start(self, daq, verbose=False):
        """ Start acquiring data or waiting for a trigger on the specified DAQ

        Args:
            daq (int)       : the input DAQ you are enabling
        """
        value = self.SD_AIN.DAQstart(daq)
        value_name = 'DAQ_start channel {}'.format(daq)
        return result_parser(value, value_name, verbose)

    def daq_start_multiple(self, daq_mask, verbose=False):
        """ Start acquiring data or waiting for a trigger on the specified DAQs

        Args:
            daq_mask (int)  : the input DAQs you are enabling, composed as a bitmask
                              where the LSB is for DAQ_0, bit 1 is for DAQ_1 etc.
        """
        value = self.SD_AIN.DAQstartMultiple(daq_mask)
        value_name = 'DAQ_start_multiple mask {:#b}'.format(daq_mask)
        return result_parser(value, value_name, verbose)

    def daq_stop(self, daq, verbose=False):
        """ Stop acquiring data on the specified DAQ

        Args:
            daq (int)       : the DAQ you are disabling
        """
        value = self.SD_AIN.DAQstop(daq)
        value_name = 'DAQ_stop channel {}'.format(daq)
        return result_parser(value, value_name, verbose)

    def daq_stop_multiple(self, daq_mask, verbose=False):
        """ Stop acquiring data on the specified DAQs

        Args:
            daq_mask (int)  : the DAQs you are triggering, composed as a bitmask
                              where the LSB is for DAQ_0, bit 1 is for DAQ_1 etc.
        """
        value = self.SD_AIN.DAQstopMultiple(daq_mask)
        value_name = 'DAQ_stop_multiple mask {:#b}'.format(daq_mask)
        return result_parser(value, value_name, verbose)

    def daq_trigger(self, daq, verbose=False):
        """ Manually trigger the specified DAQ

        Args:
            daq (int)       : the DAQ you are triggering
        """
        value = self.SD_AIN.DAQtrigger(daq)
        value_name = 'DAQ_trigger channel {}'.format(daq)
        return result_parser(value, value_name, verbose)

    def daq_trigger_multiple(self, daq_mask, verbose=False):
        """ Manually trigger the specified DAQs

        Args:
            daq_mask (int)  : the DAQs you are triggering, composed as a bitmask
                              where the LSB is for DAQ_0, bit 1 is for DAQ_1 etc.
        """
        value = self.SD_AIN.DAQtriggerMultiple(daq_mask)
        value_name = 'DAQ_trigger_multiple mask {:#b}'.format(daq_mask)
        return result_parser(value, value_name, verbose)

    def daq_flush(self, daq, verbose=False):
        """ Flush the specified DAQ

        Args:
            daq (int)       : the DAQ you are flushing
        """
        value = self.SD_AIN.DAQflush(daq)
        value_name = 'DAQ_flush channel {}'.format(daq)
        return result_parser(value, value_name, verbose)

    def daq_flush_multiple(self, daq_mask, verbose=False):
        """ Flush the specified DAQs

        Args:
            daq_mask (int)  : the DAQs you are flushing, composed as a bitmask
                              where the LSB is for DAQ_0, bit 1 is for DAQ_1 etc.
        """
        value = self.SD_AIN.DAQflushMultiple(daq_mask)
        value_name = 'DAQ_flush_multiple mask {:#b}'.format(daq_mask)
        return result_parser(value, value_name, verbose)

    def set_trigger_io(self, val, verbose=False):
        """ Write a value to the IO trigger port

        Args:
            value (int)     : the binary value to write to the IO port

        """
        # TODO: Check if the port is writable
        value = self.SD_AIN.triggerIOwrite(val)
        value_name = 'set io trigger output to {}'.format(val)
        return result_parser(value, value_name, verbose)

    def get_trigger_io(self, verbose=False):
        """ Write a value to the IO trigger port

        """
        # TODO: Check if the port is readable
        value = self.SD_AIN.triggerIOread()
        value_name = 'trigger_io'
        return result_parser(value, value_name, verbose)

    def reset_clock_phase(self, trigger_behaviour, trigger_source, skew=0.0, verbose=False):
        """ Reset the clock phase between CLKsync and CLKsys

        Args:
            trigger_behaviour (int) :
            trigger_source    (int) : the PXI trigger number
            skew           (double) : the skew between PXI_CLK10 and CLKsync in multiples of 10ns

        """
        value = self.SD_AIN.clockResetPhase(trigger_behaviour, trigger_source, skew)
        value_name = 'reset_clock_phase trigger_behaviour: {}, trigger_source: {}, skew: {}'.format(
            trigger_behaviour, trigger_source, skew)
        return result_parser(value, value_name, verbose)

    #
    # Functions used internally to set/get parameters
    #

    @staticmethod
    def set_clksys_frequency(frequency, verbose=False):
        """ Sets the CLKsys frequency

        Args:

        frequency (int)         : frequency of CLKsys in Hz

        """
        value = 0
        value_name = 'set_CLKsys_frequency not implemented'
        return result_parser(value, value_name, verbose)


# # example code
# if __name__ == '__main__':
#     my_dig = SD_DIG('test', 0, 6, 4, 1)

#     def set_digitizer(npoints = 50, cycles = 1, Vmax = 4):
#     # 1 point is 2 ns!
    
#         my_dig.data_mode(0)
        
#         my_dig.channels.ch1.set_ext_digital_trigger()
#         my_dig.channels.ch2.set_ext_digital_trigger()
#         my_dig.channels.ch3.set_ext_digital_trigger()
#         my_dig.channels.ch4.set_ext_digital_trigger()
        
#         my_dig.channels.ch1.set_channel_properties(Vmax)
#         my_dig.channels.ch2.set_channel_properties(Vmax)
#         my_dig.channels.ch3.set_channel_properties(Vmax)
#         my_dig.channels.ch4.set_channel_properties(Vmax)
        
#         my_dig.channels.ch1.points_per_cycle(npoints)
#         my_dig.channels.ch2.points_per_cycle(npoints)
#         my_dig.channels.ch3.points_per_cycle(npoints)
#         my_dig.channels.ch4.points_per_cycle(npoints)
        
#         my_dig.channels.ch1.n_cycles(1)
#         my_dig.channels.ch2.n_cycles(1)
#         my_dig.channels.ch3.n_cycles(1)
#         my_dig.channels.ch4.n_cycles(1)
        
        
#         my_dig.meas_channel([1,3])

#     set_digitizer()
#     print(my_dig.measure())
