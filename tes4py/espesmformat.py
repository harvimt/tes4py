# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 15:44:59 2015

@author: gkmachine
"""
import collections
from enum import IntEnum
from pathlib import Path
from mmap import mmap
from .binutils import *

class SubItemGenerator:
    def __init__(self, buf_name, child_factory):
        self.buf_name = buf_name
        self.child_factory = child_factory

    def __get__(self, instance, cls):
        buf = getattr(instance, self.buf_name)
        size = instance.size
        bytes_consumed = 0
        factory = self.child_factory()
        while bytes_consumed < size:
            child = factory(buf[bytes_consumed:])
            yield child
            bytes_consumed += child.total_size

class EspEsmFormat(collections.abc.Mapping):
    def __init__(self, path):
        self.path = path if isinstance(path, Path) else Path(str(path))
        self._num_groups = None

    def __enter__(self):
        self.file = f = self.path.open("r+b")
        self.mmap = mm = mmap(f.fileno(), 0)
        self.view = memoryview(mm)
        return self

    def __close__(self, *args, **kwargs):
        del self.view
        self.mmap.close()
        del self.mmap
        self.file.close()

    @property
    def header(self):
        return Record(self.view)

    @property
    def group_buf(self):
        return self.view[self.header.total_size:]

    groups = SubItemGenerator('group_buf', lambda: Group)


    def __iter__(self):
        for group in self.groups:
            yield group.label

    def __len__(self):
        if self._num_groups is None:
            ng = 0
            for group in self.groups:
                ng += 1
            self._num_groups = ng
        return self._num_groups

    def __getitem__(self, key):
        for group in self.groups:
            if group.label == key:
                return group
        raise KeyError(key)

class GroupType(IntEnum):
    top=0
    world_children=1
    interior_cell_block=2
    interior_cell_subblock=3
    exterior_cell_block=4
    exterior_cell_subblock=5
    cell_children=6
    topic_children=7
    cell_persistent=8,
    cell_temporary_children=9
    cell_visible_distant_children=10


class Group:
    def __init__(self, buffer):
        self._buffer = buffer
        assert self.type == 'GRUP'

    @property
    def buffer(self):
        return self._buffer

    @property
    def record_buffer(self):
        return self.buffer[self.header_size:]

    header_size = 20

    type = FixStrField[0:4]
    _size = ULongField[4:8]
    label = FixStrField[8:12]
    group_type = ULongField(GroupType)[12:16]
    stamp = ULongField[16:20]

    @property
    def total_size(self):
        return self._size

    @property
    def size(self):
        return self._size - self.header_size

    records = SubItemGenerator('record_buffer', lambda: Record)
    groups = SubItemGenerator('record_buffer', lambda: Group)

    def __iter__(self):
        if self.record_buffer[:4] == b'GRUP':
            return self.groups
        else:
            return self.records


class Record(collections.abc.Mapping):
    def __init__(self, buffer):
        self._buffer = buffer
        self._num_subrecords = None
        assert self.type != 'GRUP'

    @property
    def buffer(self):
        return self._buffer

    header_size = 20

    type = FixStrField[0:4]
    size = ULongField[4:8]
    flags = FlagsField(
        isesm=0x01,
        deleted=0x20,
        cast_shadows=0x200,
        is_quest_item=0x400,
        is_persistent=0x400,  # means "is quest item" or "is persistent" depending on context
        initially_disabled=0x800,
        ignored=0x1000,
        visible_when_distant=0x8000,
        dangerous_off_limits=0x20000,
        is_compressed=0x40000,
        cant_wait=0x80000,
    )[8:12]

    formid = ULongField[12:16]
    vc_info = NamedTupleField('<BBH', 'VCInfo', ['day', 'month', 'owner'])[16:20]

    @property
    def subrecord_buffer(self):
        return self.buffer[self.header_size:self.header_size + self.size]

    subrecords = SubItemGenerator('subrecord_buffer', lambda: SubRecord)

    def __iter__(self):
        for subrecords in self.subrecords:
            yield subrecords.type

    @property
    def total_size(self):
        return self.size + self.header_size

    def __len__(self):
        if self._num_subrecords is None:
            nr = 0
            for sr in self:
                nr += 1
            self._num_subrecords = nr
        return self._num_subrecords

    def __getitem__(self, key):
        for subrecord in self.subrecords:
            if subrecord.type == key:
                return subrecord
        raise KeyError(key)

class SubRecord:
    def __init__(self, buffer):
        self._buffer = buffer

    @property
    def buffer(self):
        return self._buffer

    @property
    def total_size(self):
        return self.size + self.header_size

    header_size = 6
    type = FixStrField[0:4]
    size = ULongField[4:6]

    @property
    def zstring(self):
        buf = self.buffer[self.header_size:self.total_size - 1]
        return buf.tobytes().decode('latin1')

    formid = ULongField[header_size:header_size+4]
    item_data = NamedTupleField(
        '<Lf', 'ItemData', ['gold_value', 'weight'])[header_size:header_size+8]