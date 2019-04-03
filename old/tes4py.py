#TES4Py

from mmap import mmap
from pathlib import Path
import struct

'''coyied from cookbook'''
class StructField:
    '''
    Descriptor representing a simple structure field
    '''
    def __init__(self, format, offset=None):
        self.format = format
        self.offset = offset
    def __get__(self, instance, cls):
        if instance is None:
            return self
        else:
            r =  struct.unpack_from(self.format,
                                    instance._buffer, self.offset)
            return r[0] if len(r) == 1 else r

class StructureMeta(type):
    def __init__(self, clsname, bases, clsdict):
        fields = getattr(self, '_fields_', [])
        byte_order = ''
        offset = 0
        for format, fieldname in fields:
            if format.startswith(('<','>','!','@')):
                byte_order = format[0]
                format = format[1:]
            format = byte_order + format
            setattr(self, fieldname, StructField(format, offset))
            offset += struct.calcsize(format)
        setattr(self, 'struct_size', offset)

class Structure(metaclass=StructureMeta):
    def __init__(self, bytedata):
        self._buffer = bytedata
        
'''end copied'''

# so many magic numbers

class SubRecord(Structure):
    def __init__(self, buffer, record):
        super().__init__(buffer)
        self.record = record
        
    _fields_ = [
        ('<4s', 'subrecord_type'),
        ('<H', 'size'),
    ]
    def __len__(self):
        return self.size + 6

    @property
    def blob(self):
        return self._buffer[6:][:self.size]

    @property
    def zstring(self):
        return bytes(self.blob[:-1]).decode('latin1')

    @property
    def ulong(self):
        return struct.unpack("<L", self.blob)[0]

    @property
    def data(self):
        if self.record.record_type in (b'ARMO', b'CLOT'):
            return struct.unpack("<Lf", self.blob)
        elif self.record.record_type == b'TES4':
            return self.ulong

    def __repr__(self):
        return 'SubRecord(subrecord_type=%r)' % self.subrecord_type
    
class Record(Structure):
    _fields_ = [
        ('<4s', 'record_type'),
        ('<L', 'size'),
        ('<L', 'flags'),
        ('<L', 'vc_info'), # FIXME
    ]
    
    def __repr__(self):
        return 'Record(record_type=%r)' % self.record_type
    
    @property
    def subrecords_blob(self):
        return self._buffer[4 * 5:][:self.size]

    @property
    def subrecords(self):
        blob = self.subrecords_blob
        bytes_consumed = 0
        while bytes_consumed < self.size:
            subrecord = SubRecord(blob[bytes_consumed:], self)
            bytes_consumed += len(subrecord)
            yield subrecord

    def __len__(self):
        return self.size + (4 * 5)
    
    def __getitem__(self, key):
        return [sub for sub in self.subrecords if sub.subrecord_type == key]

class Group(Structure):
    _fields_ = [
        ('<4s', 'record_type'),
        ('<L', 'size'),
        ('<4s', 'label'),
        ('<L', 'flags'),
        ('<L', 'stamp'), # FIXME
    ]
    @property
    def records_blob(self):
        return self._buffer[20:][:self.size-20]
    
    @property
    def records(self):
        blob = self.records_blob
        bytes_consumed = 0
        while bytes_consumed < (self.size - 20):
            record = Record(blob[bytes_consumed:])
            yield record
            bytes_consumed += len(record)

    def __len__(self):
        return self.size
        
FILE = Path('E:\HDSteamLib\SteamApps\common\Oblivion\Data\Oblivion.esm')

f = FILE.open("r+b")
mm = mmap(f.fileno(), 0)
mv = memoryview(mm)
rg = Record(mv)
bytes_consumed = len(rg)
groups = {}
while bytes_consumed < len(mv):
    group = Group(mv[bytes_consumed:])
    groups[group.label] = group
    bytes_consumed += len(group)

#f.close()  # FIXME
