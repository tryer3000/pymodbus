#!/usr/bin/env python
'''
Pymodbus Asynchronous Client Examples
--------------------------------------------------------------------------

The following is an example of how to use the asyncio modbus
client implementation from pymodbus.
'''
# from pymodbus.constants import Defaults
from pymodbus.client.async3 import ModbusRTUClient
import asyncio
import logging
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.DEBUG)

loop = asyncio.get_event_loop()


async def test():
    # print('is connected', client._connected)
    client = await ModbusRTUClient('/dev/pts/22')
    await client.sentinel
    rq = await client.write_coil(1, True)
    rr = await client.read_coils(1, 1)
    assert(rq.function_code < 0x80)     # test that we are not an error
    assert(rr.bits[0] is True)          # test the expected value

    rq = await client.write_coils(1, [True] * 8)
    rr = await client.read_coils(1, 8)
    assert(rq.function_code < 0x80)     # test that we are not an error
    assert(rr.bits == [True] * 8)         # test the expected value

    rq = await client.write_coils(1, [False] * 8)
    rr = await client.read_discrete_inputs(1, 8)
    assert(rq.function_code < 0x80)     # test that we are not an error
    assert(rr.bits == [True] * 8)         # test the expected value

    rq = await client.write_register(1, 10)
    rr = await client.read_holding_registers(1, 1)
    assert(rq.function_code < 0x80)     # test that we are not an error
    assert(rr.registers[0] == 10)       # test the expected value

    rq = await client.write_registers(1, [10] * 8)
    rr = await client.read_input_registers(1, 8)
    assert(rq.function_code < 0x80)     # test that we are not an error
    assert(rr.registers == [17] * 8)      # test the expected value

    arguments = {
        'read_address': 1,
        'read_count': 8,
        'write_address': 1,
        'write_registers': [20] * 8,
    }
    rq = await client.readwrite_registers(**arguments)
    rr = await client.read_input_registers(1, 8)
    assert(rq.registers == [20] * 8)  # test the expected value
    assert(rr.registers == [17] * 8)  # test the expected value


loop.run_until_complete(test())
loop.close()
