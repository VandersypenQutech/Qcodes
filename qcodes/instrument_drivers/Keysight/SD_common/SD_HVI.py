from qcodes.instument.base import Instrument

try:
    import keysightSD1
except:
    raise ImportError('to use the Keysight SD drivers'
                      'install the keysightSD1 module'
                      '(www.keysight.com/main/software.jspx?ckey=2784055)')

# -----------------------------------------------------------------------------


class SD_HVI(Instrument):

    def __init__(self, name, chassis, slot, index, **kwargs):
        super().__init__(name, **kwargs)
        self._index_ = index
        self._hvi_ = keysightSD1.SD_HVI()
        result_code = self._hvi_.assignHardwareWithIndexAndSlot(index, chassis,
                                                                slot)
        if result_code <= 0:
            raise Exception('Could not open SD_HVI '
                            'error code {}'.format(result_code))

        self.add_parameter('open',
                           label='open',
                           get_cmd=self._hvi_.isOpen,
                           docstring='Indicating if device is open, True'
                                     ' (open) or False (closed)')

    # def get_open(self):
    #     self._hvi_.isOp

    def open(self):
        pass

    def close(self):
        pass

    def start(self):
        pass

    def resume(self):
        pass

    def stop(self):
        pass

    def compile(self):
        pass

    def load(self):
        pass

    # def compilation_error_message(self):
    #     pass

    # --- HVI hardware

    def assign_hardware(self, index: int):
        pass

    # --- HVI modules

    def get_number_of_modules(self):
        pass

    def get_module_name(self):
        pass

    def get_module_index(self):
        pass

    def get_module(self):  # index, chasis, slot
        pass

    def write_constant(self):  # index, (float or int)
        pass

    def read_constant(self):  # index, (float or int)
        pass

    # --- Unknown

    def write_register(self):
        raise NotImplementedError

    def read_register(self):
        raise NotImplementedError
