"""
Implementation of a Modbus Client Using asyncio
"""
import time
from serial.aio import create_serial_connection
from asyncio import Future, Protocol, get_event_loop
from pymodbus.constants import Defaults
from pymodbus.compat import byte2int
from pymodbus.factory import ClientDecoder
from pymodbus.exceptions import ConnectionException
from pymodbus.transaction import ModbusSocketFramer
from pymodbus.transaction import FifoTransactionManager
from pymodbus.transaction import DictTransactionManager
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.client.common import ModbusClientMixin

import logging
_logger = logging.getLogger(__name__)


class ModbusTCPClientProtocol(Protocol, ModbusClientMixin):
    '''
    This represents the base modbus client protocol.  All the application
    layer code is deferred to a higher level wrapper.
    '''

    def __init__(self, framer=None, **kwargs):
        ''' Initializes the framer module

        :param framer: The framer to use for the protocol
        '''
        self._connected = False
        self.framer = framer or ModbusSocketFramer(ClientDecoder())
        if isinstance(self.framer, ModbusSocketFramer):
            self.transaction = DictTransactionManager(self, **kwargs)
        else:
            self.transaction = FifoTransactionManager(self, **kwargs)
        self.sentinel = Future()

    def connection_made(self, transport):
        ''' Called upon a successful client connection.
        '''
        _logger.debug("Client connected to modbus server")
        self._connected = True
        self.sentinel.set_result(1)
        self.transport = transport

    def connection_lost(self, reason):
        ''' Called upon a client disconnect

        :param reason: The reason for the disconnect
        '''
        _logger.debug("Client disconnected from modbus server: %s" % reason)
        self._connected = False
        for tid in list(self.transaction):
            d = Future()
            exc = ConnectionException('Connection lost during request')
            d.set_exception(exc)
            self.transaction.getTransaction(tid).errback(d)

    def data_received(self, data):
        ''' Get response, check for valid message, decode result

        :param data: The data returned from the server
        '''
        self.framer.processIncomingPacket(data, self._handleResponse)

    def execute(self, request):
        ''' Starts the producer to send the next request to
        consumer.write(Frame(request))
        '''
        request.transaction_id = self.transaction.getNextTID()
        packet = self.framer.buildPacket(request)
        self.transport.write(packet)
        return self._buildResponse(request.transaction_id)

    def _handleResponse(self, reply):
        ''' Handle the processed response and link to correct deferred

        :param reply: The reply to process
        '''
        if reply is not None:
            tid = reply.transaction_id
            handler = self.transaction.getTransaction(tid)
            if handler:
                handler.set_result(reply)
            else:
                _logger.debug("Unrequested message: " + str(reply))

    def _buildResponse(self, tid):
        ''' Helper method to return a deferred response
        for the current request.

        :param tid: The transaction identifier for this response
        :returns: A defer linked to the latest request
        '''
        d = Future()
        if not self._connected:
            d.set_exception(ConnectionException('Client is not connected'))

        self.transaction.addTransaction(d, tid)
        return d


class ModbusRTUClientProtocol(Protocol, ModbusClientMixin):
    def __init__(self, **kwargs):
        ''' Initializes the framer module

        :param framer: The framer to use for the protocol
        '''
        self._connected = False
        self.baudrate = kwargs.get('baudrate', Defaults.Baudrate)
        self.framer = ModbusRtuFramer(ClientDecoder())
        if isinstance(self.framer, ModbusSocketFramer):
            self.transaction = DictTransactionManager(self, **kwargs)
        else:
            self.transaction = FifoTransactionManager(self, **kwargs)

        if self.baudrate > 19200:
            self._silent_interval = 1.75 / 1000  # ms
        else:
            self._silent_interval = 3.5 * (1 + 8 + 2) / self.baudrate
        self.sentinel = Future()

    def connection_made(self, transport):
        ''' Called upon a successful client connection.
        '''
        _logger.debug("Client connected to modbus server")
        self._connected = True
        self._last_frame_end = time.time()
        self.transport = transport
        self.sentinel.set_result(1)

    def connection_lost(self, reason):
        ''' Called upon a client disconnect

        :param reason: The reason for the disconnect
        '''
        _logger.debug("Client disconnected from modbus server: %s" % reason)
        self._connected = False
        for tid in list(self.transaction):
            d = Future()
            exc = ConnectionException('Connection lost during request')
            d.set_exception(exc)
            self.transaction.getTransaction(tid).errback(d)

    def data_received(self, data):
        ''' Get response, check for valid message, decode result

        :param data: The data returned from the server
        '''
        self._last_frame_end = time.time()
        self.framer.processIncomingPacket(data, self._handleResponse)

    def execute(self, request):
        ''' Starts the producer to send the next request to
        consumer.write(Frame(request))
        '''
        request.transaction_id = self.transaction.getNextTID()
        ts = time.time()
        if ts < self._last_frame_end + self._silent_interval:
            _logger.debug("will sleep to wait for 3.5 char")
            time.sleep(self._last_frame_end + self._silent_interval - ts)

        try:
            in_waiting = (
                "in_waiting"
                if hasattr(self.transport.serial, "in_waiting")
                else "inWaiting")
            if in_waiting == "in_waiting":
                waitingbytes = getattr(self.transport.serial, in_waiting)
            else:
                waitingbytes = getattr(self.transport.serial, in_waiting)()
            if waitingbytes:
                result = self.transport.read(waitingbytes)
                if _logger.isEnabledFor(logging.WARNING):
                    _ = " ".join([hex(byte2int(x)) for x in result])
                    _logger.warning("cleanup recv buffer before send: " + _)
        except NotImplementedError:
            pass

        packet = self.framer.buildPacket(request)
        self.transport.write(packet)
        self._last_frame_end = time.time()
        return self._buildResponse(request.transaction_id)

    def _handleResponse(self, reply):
        ''' Handle the processed response and link to correct deferred

        :param reply: The reply to process
        '''
        if reply is not None:
            tid = reply.transaction_id
            handler = self.transaction.getTransaction(tid)
            if handler:
                handler.set_result(reply)
            else:
                _logger.debug("Unrequested message: " + str(reply))

    def _buildResponse(self, tid):
        ''' Helper method to return a deferred response
        for the current request.

        :param tid: The transaction identifier for this response
        :returns: A defer linked to the latest request
        '''
        d = Future()
        if not self._connected:
            d.set_exception(ConnectionException('Client is not connected'))

        self.transaction.addTransaction(d, tid)
        return d


async def ModbusClient(host, port):
    ioloop = get_event_loop()
    transport, protocol = await ioloop.create_connection(
        lambda: ModbusTCPClientProtocol(),
        'localhost', 5020
    )
    return protocol


async def ModbusRTUClient(path, **kwargs):
    ioloop = get_event_loop()
    stopbits = kwargs.get('stopbits', Defaults.Stopbits)
    bytesize = kwargs.get('bytesize', Defaults.Bytesize)
    parity = kwargs.get('parity', Defaults.Parity)
    baudrate = kwargs.get('baudrate', Defaults.Baudrate)
    timeout = kwargs.get('timeout', Defaults.Timeout)

    transport, protocol = await create_serial_connection(
        ioloop, lambda: ModbusRTUClientProtocol(baudrate=baudrate), path,
        timeout=timeout, bytesize=bytesize,
        stopbits=stopbits, baudrate=baudrate, parity=parity)
    return protocol
