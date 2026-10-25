"""Commands share the serial reader; HTTP workers never open another USB port."""
import copy
import json
import queue
import threading
import uuid

from .models import SENSOR


class SensorControl:
    def __init__(self):
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.outgoing = queue.Queue()
        self.connected = False
        self.info = None
        self.pending = {}

    def snapshot(self):
        with self.lock:
            return {'connected': self.connected, 'configuration': copy.deepcopy(self.info)}

    def connect(self):
        with self.lock:
            self.connected = True
            self.info = None

    def disconnect(self):
        with self.lock:
            self.connected = False
            self.info = None
            for pending in self.pending.values():
                pending['error'] = 'Sensor disconnected; check its effective configuration after reconnecting'
                pending['done'].set()

    @staticmethod
    def wire(identifier, action, values=None):
        return ('WIDS_CMD ' + json.dumps({'v': 1, 'id': identifier, 'action': action,
                                         'settings': values or {}}, separators=(',', ':')) + '\n').encode()

    def receive(self, event):
        if event.get('kind') != 'config_ack':
            return False
        with self.lock:
            if event.get('ok') is True:
                if not self.valid_acknowledgement(event):
                    return True
                self.info = {'values': event['config'], 'capabilities': event.get('capabilities', {}),
                             'ble_status': event.get('ble_status')}
            pending = self.pending.get(event.get('id'))
            if pending:
                pending['response'] = event
                pending['done'].set()
        return True

    @staticmethod
    def valid_acknowledgement(event):
        values, caps = event.get('config'), event.get('capabilities')
        if not isinstance(values, dict) or not isinstance(caps, dict):
            return False
        if not isinstance(values.get('sensor_id'), str) or not SENSOR.fullmatch(values['sensor_id']):
            return False
        bands, channels = caps.get('bands'), caps.get('channels')
        if not isinstance(bands, list) or not bands or any(band not in ('2.4', '5') for band in bands):
            return False
        if not isinstance(channels, dict):
            return False
        for band in bands:
            offered = channels.get(band)
            low, high = (1, 14) if band == '2.4' else (36, 177)
            if not isinstance(offered, list) or not offered or len(offered) > 177 or any(
                type(channel) is not int or not low <= channel <= high for channel in offered
            ):
                return False
        band = values.get('band')
        if not isinstance(band, str) or band not in bands or type(values.get('channel')) is not int or values['channel'] not in channels[band]:
            return False
        for name, high in [('beacon_sample_n', 1000), ('heartbeat_seconds', 300)]:
            if type(values.get(name)) is not int or not 1 <= values[name] <= high:
                return False
        if caps.get('ble') is True:
            if type(values.get('ble_enabled')) is not bool:
                return False
            if any(type(values.get(name)) is not int or not 10 <= values[name] <= 10240
                   for name in ('ble_interval_ms', 'ble_window_ms')):
                return False
            if values['ble_window_ms'] > values['ble_interval_ms']:
                return False
            status = event.get('ble_status')
            if not isinstance(status, dict) or type(status.get('scanning')) is not bool:
                return False
            if type(status.get('error')) is not int or not -(2**31) <= status['error'] < 2**31:
                return False
            if any(type(status.get(name)) is not int or not 0 <= status[name] < 2**32 for name in ('captured', 'dropped')):
                return False
        return all(isinstance(caps.get(name), str) and len(caps[name]) <= 80
                   for name in ('chip', 'console'))

    def validate(self, values):
        if not isinstance(values, dict) or not values or values.keys() - {
            'sensor_id', 'band', 'channel', 'beacon_sample_n', 'heartbeat_seconds',
            'ble_enabled', 'ble_interval_ms', 'ble_window_ms'
        }:
            raise ValueError('Unknown or empty sensor settings')
        with self.lock:
            if not self.connected:
                raise ConnectionError('Sensor is disconnected')
            if self.info is None:
                raise ConnectionError('Sensor firmware has not reported runtime configuration support')
            current = {**self.info['values'], **values}
            capabilities = self.info['capabilities']
        if not isinstance(current.get('sensor_id'), str) or not SENSOR.fullmatch(current['sensor_id']):
            raise ValueError('Sensor ID must contain 1..40 letters, digits, dots, dashes or underscores')
        band = current.get('band')
        if not isinstance(band, str) or band not in capabilities.get('bands', []):
            raise ValueError('Unsupported receive band')
        if type(current.get('channel')) is not int or current['channel'] not in capabilities.get('channels', {}).get(band, []):
            raise ValueError('Channel is not supported in the selected band and regulatory profile')
        for name, high in [('beacon_sample_n', 1000), ('heartbeat_seconds', 300)]:
            if type(current.get(name)) is not int or not 1 <= current[name] <= high:
                raise ValueError(f'{name} must be an integer in 1..{high}')
        names = ['sensor_id', 'band', 'channel', 'beacon_sample_n', 'heartbeat_seconds']
        if any(name.startswith('ble_') for name in values) and capabilities.get('ble') is not True:
            raise ValueError('Sensor does not support BLE monitoring; update firmware')
        if capabilities.get('ble') is True:
            if type(current.get('ble_enabled')) is not bool:
                raise ValueError('BLE enabled must be boolean')
            for name in ('ble_interval_ms', 'ble_window_ms'):
                if type(current.get(name)) is not int or not 10 <= current[name] <= 10240:
                    raise ValueError('BLE scan timing must be an integer in 10..10240 ms')
            if current['ble_window_ms'] > current['ble_interval_ms']:
                raise ValueError('BLE scan window must not exceed interval')
            names += ['ble_enabled', 'ble_interval_ms', 'ble_window_ms']
        return {name: current[name] for name in names}

    def apply(self, values, timeout=8):
        with self.operation:
            values = self.validate(values)
            identifier = uuid.uuid4().hex
            pending = {'done': threading.Event()}
            with self.lock:
                self.pending[identifier] = pending
                self.outgoing.put((identifier, self.wire(identifier, 'set_config', values)))
            try:
                if not pending['done'].wait(timeout):
                    raise TimeoutError('Sensor acknowledgement timed out; settings may have applied. Reload Configuration to confirm before retrying.')
                if 'error' in pending:
                    raise ConnectionError(pending['error'])
                response = pending['response']
                if response.get('ok') is not True:
                    raise ValueError(response.get('error', 'Sensor rejected configuration'))
                if any(response['config'].get(name) != value for name, value in values.items()):
                    raise ValueError('Sensor acknowledged different settings; reload Configuration to inspect the effective values')
                return self.snapshot()
            finally:
                with self.lock:
                    self.pending.pop(identifier, None)

    def send_queued(self, device):
        while True:
            try:
                identifier, wire = self.outgoing.get_nowait()
            except queue.Empty:
                return
            with self.lock:
                # Expired/disconnected requests must not execute later.
                pending = self.pending.get(identifier)
                if pending is not None and not pending['done'].is_set():
                    device.write(wire)
