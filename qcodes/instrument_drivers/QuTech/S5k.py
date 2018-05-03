# -*- coding: utf-8 -*-
"""
Created on Mon Apr 30 13:35:18 2018

@author: Sjaak van Diepen
email: c.j.vandiepen@tudelft.nl
"""
import warnings
from qcodes import Instrument

try:
    from spirack import S5k_module
except ImportError:
    raise ImportError(('The S5k_module class could not be found. '
                       'Try installing it using pip install spirack'))

class S5k(Instrument):
    """ Qcodes driver for the S5k awg SPI-rack module. """
    def __init__(self, name, spi_rack, module, **kwargs):
        """ Create instrument for the S5k awg SPI-rack module.
        
        Args:
            name (str): name of the instrument.

            spi_rack (SPI_rack): instance of the SPI_rack class as defined in
                the spirack package. This class manages communication with the
                individual modules.

            module (int): module number as set on the hardware.
        """
        super().__init__(name, **kwargs)
        
        self.s5k = S5k_module(spi_rack, module)
        
        self.add_parameter('clock_source', 
                           get_cmd=self.get_clock_source,
                           set_cmd=self.s5k.set_clock_source)
        
        for i in range(1, 17):
            self.add_parameter('ch{}_gain'.format(i),
                               get_cmd=self.get_digital_gain,
                               set_cmd=self.set_digital_gain)
            self.add_parameter('ch{}_clock_div'.format(i),
                               set_cmd=self.set_clock_division)
        
        for DAC in range(1,9):
            self.s5k.set_clock_division(DAC, 4)
        for DAC in range(9, 17):
            self.s5k.set_clock_division(DAC, 400)
            
        for DAC in range(1, 17):
            self.s5k.set_waveform_mode(DAC, 'AWG')
            self.s5k.set_digital_gain(DAC, 0.2)
            
    def run(self):
        self.s5k.run_module(True)
        
    def stop(self):
        self.s5k.run_module(False)
    
    def get_clock_source(self):
        return self.s5k.reference
    
    def set_clock_division(self, channel, division):
        if division % 2 is not 0 or division > 510:
            warnings.warn('Clock division must be an even number between 2-510.')
        self.s5k.set_clock_division(channel, division)
    
    def get_digital_gain(self, channel):
        return self.s5k.DAC_dgain[channel-1]
    
    def send_waveform(self, waveform, channel):
        pass