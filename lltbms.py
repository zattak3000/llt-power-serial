import serial
import struct
from datetime import date

# Byte Constants
START = b"\xDD"
STOP = b"\x77"
READ = b"\xA5"
WRITE = b"\x5A"

# Commands
STATUS = b'\x03'
VOLTAGE = b'\x04'
VERSION = b'\x05'

# MOSFET Modes
BLOCK_CHARGE = b'\x01'
BLOCK_DISCHARGE = b'\x02'
BLOCK_BOTH = b'\x03'

# Error names
ERRORS = [
    "Cell Block Over-volt",
    "Cell Block Under-volt",
    "Battery Over-volt",
    "Battery Under-volt",
    "Charging Temp High",
    "Charging Temp Low",
    "Discharging Temp High",
    "Discharging Temp Low",
    "Charging Over-current",
    "Discharging Over-current",
    "Short Circuit",
    "IC Error",
    "MOSFET Lock",
    "Reserved 1",
    "Reserved 2",
    "Reserved 3",
]

class BMS():
    def __init__(self, port, baud=9600) -> None:
        self.port = serial.Serial(port, baud)
        self.get_info()

    def get_version(self):
        response = self.send_command(VERSION)
        return "LH-" + response.data.decode("utf-8")

    def get_info(self):
        response = self.send_command(STATUS)

        # TODO make struct object constant
        values = struct.unpack(">Hh7H5B", response.data[:23])
        
        # TODO make parsed response more object-y
        # TODO Expand bitfields into lists

        prot_status = []
        for i in range(16):
            if (values[8] >> i) & 1:
                prot_status.append(ERRORS[i])

        info = {
            "Voltage": values[0] / 100,
            "Current": values[1] / 100,
            "Residual Capacity": values[2] / 100,
            "Nominal Capacity": values[3] / 100,
            "Cycle Life": values[4],
            "Product Date": date(
                year = 2000 + (values[5] >> 9),
                month = (values[5] >> 5) & 0xf,
                day = values[5] & 0x1f
            ),
            "Balance Status": values[6],
            "Balance Status High": values[7],
            "Protection Status": prot_status,
            "Version": values[9] / 10,
            "Relative SOC": values[10],
            "FET Status": values[11],
            "NTC Temp": []
        }

        for ntc in struct.unpack(f">{values[13]}H", response.data[23:]):
            f = (ntc - 2731) / 10 * 9/5 + 32
            info["NTC Temp"].append(f)

        return info

    def get_voltages(self):
        response = self.send_command(VOLTAGE)

        num_cells = len(response.data) // 2

        voltages = struct.unpack(f">{num_cells}H", response.data)
        voltages = [i / 1000 for i in voltages]
        
        return voltages

    # TODO create individual toggle functions?
    # TODO figure out why it doesnt work
    def set_mosfet(self, mode):
        response = self.send_command(b'\xE2', WRITE, b'\x00' + mode)

        return response

    def send_command(self, command, mode=READ, data=b''):
        self.port.write(bytes(Message(command, mode, data)))
        
        if self.port.read() != START:
            raise ConnectionError("Incorrect start bit")

        response = START + self.port.read_until(STOP)

        message = Message.from_bytes(response)

        # TODO Better bad checksum handling (limited retry?)
        if not message.verify_checksum():
            raise ConnectionError("Bad Checksum")

        if message.command != b'\x00':
            raise RuntimeError("Command Error from BMS")
        
        return message

class Message():
    def __init__(self, command=b'\x03', status=READ, data=b'', checksum=None) -> None:
        '''
        Create a message to be sent to the BMS
        '''
        # TODO max length check and a bunch of other error checking
        # TODO add checksum verification for recieved messages
        
        self.status = status
        self.command = command
        self.length = struct.pack("B", len(data))
        self.data = data

        if checksum:
            self.checksum = checksum

        else:
            self.checksum = self.__gen_checksum()

    def from_bytes(b):
        '''
        Parse a message in byte form to a Message object
        '''
        self = Message()
        # TODO replace with struct unpacks?
        self.status = b[1].to_bytes(1, 'big')
        self.command = b[2].to_bytes(1, 'big')
        self.length = b[3].to_bytes(1, 'big')
        self.data = b[4: 4 + b[3]]
        self.checksum = b[4 + b[3]: 5 + b[3] + 1]

        return self

    def __bytes__(self):
        b = START
        b += self.status
        b += self.command
        b += self.length
        b += self.data
        b += self.checksum
        b += STOP

        return b

    def __gen_checksum(self):
        '''
        Generate the checksum for a Message object
        '''
        checksum = ~sum(self.command + self.length + self.data) + 1
        return struct.pack(">h", checksum)
        

    def verify_checksum(self):
        '''
        Verify if the checksum for a given message is correct
        '''
        if self.checksum == self.__gen_checksum():
            return True
        else:
            return False

    def __repr__(self) -> str:
        return str({
            "status": self.status,
            "command": self.command,
            "length": self.length,
            "data": self.data,
            "checksum": self.checksum
        })

    
if __name__ == '__main__':

    thebms = BMS('COM4')

    print("BMS Version".center(50,'-'))

    ver = thebms.get_version()

    print(ver)

    # thebms.set_mosfet(b'\x00')

    print()
    print("BMS Info".center(50,'-'))

    status = thebms.get_info()

    for i in status:
        print(f"{i}:", status[i])

    print()
    print("Cell Voltages".center(50,'-'))

    voltages = thebms.get_voltages()

    for i, j in enumerate(voltages):
        print(f"Cell {i + 1}: {j} V")