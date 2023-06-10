
GET_DTC_COMMAND = "03"
CLEAR_DTC_COMMAND = "04"
GET_FREEZE_DTC_COMMAND = "07"


def hex_to_int(string):
    if string:
        return int(string, 16)
    return 0


def a(hex):
    return hex_to_int(hex[0:1])


def b(hex):
    return hex_to_int(hex[2:3])


def c(hex):
    return hex_to_int(hex[4:5])


def d(hex):
    return hex_to_int(hex[6:7])


# __________________________________________________________________________
def decrypt_dtc_code(code):
    """Returns the 5-digit DTC code from hex encoding"""
    dtc = []
    for i in range(0, 3):
        if len(code) < 4:
            raise "Tried to decode bad DTC: %s" % code

        tc = hex_to_int(code[0]) >> 2  # typecode

        match tc:
            case 0:
                dtc_type = "P"
            case 1:
                dtc_type = "C"
            case 2:
                dtc_type = "B"
            case 3:
                dtc_type = "U"
            case _:
                raise ValueError("Invalid DTC Type")

        dig1 = hex_to_int(code[0]) & 3
        dig2 = hex_to_int(code[1])
        dig3 = hex_to_int(code[2])
        dig4 = hex_to_int(code[3])

        dtc.append(f"{dtc_type}{dig1}{dig2}{dig3}{dig4}")

        code = code[4:]

    return dtc


def get_dtc(self):
    """Returns a list of all pending DTC codes. Each element consists of
      a 2-tuple: (DTC code (string), Code description (string) )"""
    dtcLetters = ["P", "C", "B", "U"]
    r = self.sensor(1)[1]  # data
    dtcNumber = r[0]
    mil = r[1]
    DTCCodes = []

    print(f"Number of stored DTC: {dtcNumber} MIL: {mil}")
    # get all DTC, 3 per mesg response
    for i in range(0, ((int(dtcNumber) + 2) / 3)):
        self.send_command(GET_DTC_COMMAND)
        res = self.get_result()
        print("DTC result:", res)
        for i in range(0, 3):
            val1 = hex_to_int(res[3 + i * 6:5 + i * 6])
            val2 = hex_to_int(res[6 + i * 6:8 + i * 6])  # get DTC codes from response (3 DTC each 2 bytes)
            val = (val1 << 8) + val2  # DTC val as int

            if val == 0:  # skip fill of last packet
                break

            DTCStr = dtcLetters[(val & 0xC000) > 14] + str((val & 0x3000) >> 12) + str(val & 0x0fff)

            DTCCodes.append(["Active", DTCStr])

    # read mode 7
    self.send_command(GET_FREEZE_DTC_COMMAND)
    res = self.get_result()

    if res[:7] == "NO DATA":  # no freeze frame
        return DTCCodes

    print("DTC freeze result:", res)
    for i in range(0, 3):
        val1 = hex_to_int(res[3 + i * 6:5 + i * 6])
        val2 = hex_to_int(res[6 + i * 6:8 + i * 6])  # get DTC codes from response (3 DTC each 2 bytes)
        val = (val1 << 8) + val2  # DTC val as int

        if val == 0:  # skip fill of last packet
            break

        DTCStr = dtcLetters[(val & 0xC000) > 14] + str((val & 0x3000) >> 12) + str(val & 0x0fff)
        DTCCodes.append(["Passive", DTCStr])

    return DTCCodes


def clear_dtc(self):
    """Clears all DTCs and freeze frame data"""
    self.send_command(CLEAR_DTC_COMMAND)
    r = self.get_result()
    return r


def dtc_decrypt(code):
    # first byte is byte after PID and without spaces
    num = a(code[:2])  # A byte
    res = []

    if num & 0x80:  # is mil light on
        mil = 1
    else:
        mil = 0

    # bit 0-6 are the number of dtc's.
    num = num & 0x7f

    res.append(num)
    res.append(mil)

    numB = b(code[2:4])  # B byte

    for i in range(0, 3):
        res.append(((numB >> i) & 0x01) + ((numB >> (3 + i)) & 0x02))

    numC = c(code[4:6])  # C byte
    numD = d(code[6:8])  # D byte

    for i in range(0, 7):
        res.append(((numC >> i) & 0x01) + (((numD >> i) & 0x01) << 1))

    res.append(((numD >> 7) & 0x01))  # EGR SystemC7  bit of different

    return res
