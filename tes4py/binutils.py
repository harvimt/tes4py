"""
Created on Sat Apr 18 15:42:19 2015
"""
from collections import namedtuple
import struct

class Flags:
    def __init__(self, val, fields=None, **kwargs):
        self._flags = fields or kwargs
        self._val = val

    def __getattr__(self, flag):
        try:
            return bool(self._flags[flag] & self._val)
        except KeyError as ex:
            raise AttributeError from ex

    def __repr__(self):
        return '<Flags ' + ', '.join(
            '{!s}={!r}'.format(flag, getattr(self, flag))
            for flag in self._flags
        ) + '>'


class StructFieldMeta(type):
    def __getitem__(self, offset):
        return self()[offset]


class StructField(metaclass=StructFieldMeta):
    def __init__(self):
        self.offset = None

    def transform(self, buffer):
        raise NotImplemented

    def __get__(self, instance, cls):
        return self.transform(instance.buffer[self.offset])

    def __getitem__(self, offset):
        self.offset = offset
        return self


class FixStrField(StructField):
    def transform(self, buffer):
        return buffer.tobytes().decode('latin1')


class ULongField(StructField):
    def __init__(self, int_type=None):
        self._int_type = int_type

    def transform(self, buffer):
        val = int.from_bytes(buffer, 'little', signed=False)
        if self._int_type:
            val = self._int_type(val)
        return val


class NamedTupleField(StructField):
    def __init__(self, struct_fmt, name, fields):
        self._struct_fmt = struct_fmt
        self._namedtuple = namedtuple(name, fields)

    def transform(self, buffer):
        return self._namedtuple(*struct.unpack_from(self._struct_fmt, buffer))


class FlagsField(StructField):
    def __init__(self, **flags):
        self._flags = flags

    def transform(self, buffer):
        val = int.from_bytes(buffer, 'little', signed=False)
        return Flags(val, self._flags)