# -*- coding: utf-8 -*-
"""
Created on Sat Apr 18 15:44:59 2015

@author: gkmachine
"""
import collections
import collections.abc
from enum import IntEnum
from pathlib import Path
from mmap import mmap
from .binutils import *
import weakref
import contextlib

class SubItemGenerator:
    def __init__(self, child_factory):
        self.child_factory = child_factory

    def __get__(self, instance, cls):
        return instance.generate_subitems(self.child_factory())

class BaseRecord:
    # properties must implement
    header_size = None
    total_size = None
    size = None

    def __init__(self, buffer, offset):
        self._buffer = buffer
        self._offset = offset

    @property
    def buffer(self):
        return self._buffer[self._offset: self._offset + self.total_size]

    @property
    def body_buffer(self):
        return self._buffer[self._offset + self.header_size: self._offset + self.total_size]

    def generate_subitems(self, factory):
        buf = self._buffer
        size = self.size
        bytes_consumed = 0
        factory = factory
        while bytes_consumed < size:
            child = factory(buf, self._offset + self.header_size + bytes_consumed)
            yield child
            bytes_consumed += child.total_size

class EspEsmFormat(BaseRecord, collections.abc.Mapping):
    def __init__(self, vieworpath = None):
        if isinstance(vieworpath, memoryview):
            self.view = vieworpath
        else:
            path = vieworpath
            self.path = path if isinstance(path, Path) else Path(str(path))
        self._num_groups = None
        self._groups_cache = None

    def __enter__(self):
        self._exit_stack = stack = contextlib.ExitStack()
        self._file = f = stack.enter_context(self.path.open("r+b"))
        self._mmap = mm = stack.enter_context(mmap(f.fileno(), 0))
        self.view = stack.enter_context(memoryview(mm))
        self.header_size = self.header.total_size
        self.total_size = len(self.view)
        self.size = len(self.view) - self.header_size
        self._groups_cache = None
        return self

    def __exit__(self, *args, **kwargs):
        #del self.view
        #del self._mmap
        #del self._file
        self._exit_stack.close()

    @property
    def _buffer(self):
        return self.view

    @property
    def header(self):
        return Record(self.view, 0)

    @property
    def buffer(self):
        return self.view

    @property
    def body_buffer(self):
        return self.view[self.header_size:]

    _offset = 0

    @property
    def groups(self):
        if self._groups_cache is None:
            self._groups_cache = [
                g for g in self._groups
                if g.label not in ('WRLD', 'CELL', 'DIAL')
                # exclude irregular groups for now
            ]
        return self._groups_cache

    _groups = SubItemGenerator(lambda: Group)

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


class Group(BaseRecord):
    def __init__(self, buffer, offset):
        super().__init__(buffer, offset)
        type, total_size = struct.unpack_from('<4sL', buffer[offset:])
        self.type = type.decode('latin1')
        self.total_size = total_size
        self.size = total_size - self.header_size
        self._records_cache = None

    header_size = 20

    label = FixStrField[8:12]
    group_type = ULongField(GroupType)[12:16]
    stamp = ULongField[16:20]

    @property
    def records(self):
        if self._records_cache is None:
            self._records_cache = list(self._records)
        return self._records_cache

    _records = SubItemGenerator(lambda: Record)
    groups = SubItemGenerator(lambda: Group)


class Record(BaseRecord, collections.abc.Mapping):
    def __init__(self, buffer, offset):
        super().__init__(buffer, offset)
        self._num_subrecords = None
        type, size = struct.unpack_from('<4sL', buffer[offset:])
        self.type = type.decode('latin1')
        self.size = size
        self.total_size = size + self.header_size

        assert self.type != 'GRUP'


    header_size = 20

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

    subrecords = SubItemGenerator(lambda: SubRecord)

    def __iter__(self):
        for subrecords in self.subrecords:
            yield subrecords.type

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

class SubRecord(BaseRecord):
    def __init__(self, buffer, offset):
        super().__init__(buffer, offset)
        type, size = struct.unpack_from('<4sH', buffer[offset:])
        self.type = type.decode('latin1')
        self.size = size
        self.total_size = size + self.header_size

    header_size = 6

    @property
    def zstring(self):
        buf = self.body_buffer[:-1].tobytes()
        assert self.body_buffer[-1] == 0
        assert b'\0' not in buf
        return buf.decode('latin1')

    formid = ULongField[header_size:header_size+4]
    item_data = NamedTupleField(
        '<Lf', 'ItemData', ['gold_value', 'weight'])[header_size:header_size+8]