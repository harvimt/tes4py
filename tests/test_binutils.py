
import pytest
from tes4py.binutils import *
from enum import IntEnum

def test_flags():
    flags = Flags(0b101, a=0b010, b=0b001, c=0b011)
    assert not flags.a
    assert flags.b
    assert flags.c
    assert isinstance(repr(flags), str)
    with pytest.raises(AttributeError):
        assert flags.d

DATA = b'\x42\x00' + 0b101.to_bytes(1, 'little') + b'HelloWorld!\0'
DATASTR = DATA.decode('latin1')


class DummyEnum(IntEnum):
    life_universe_everything = 0x42
    dummy = 0

@pytest.fixture
def dummystruct():

    class DummyStruct:
        def __init__(self, buffer):
            self.buffer = buffer
        buffer = None
        fixstr = FixStrField[4:6]
        numfield = ULongField[0:2]
        enumfield = ULongField(DummyEnum)[0:2]
        tfield = NamedTupleField('<B1s', 'TField', ['a', 'b'])[0:2]
        flags = FlagsField(a=0b010, b=0b001, c=0b011)[2:3]

    return DummyStruct(memoryview(DATA))

def test_fixstrfield(dummystruct):
    assert DATASTR[4:6] == dummystruct.fixstr

def test_ulongfield(dummystruct):
    assert dummystruct.numfield == 0x42

def test_enumfield(dummystruct):
    assert dummystruct.enumfield == DummyEnum.life_universe_everything

def test_namedtuplefield(dummystruct):
    assert dummystruct.tfield.a == 0x42
    assert dummystruct.tfield.b == b'\0'

def test_flagfield(dummystruct):
    assert not dummystruct.flags.a
    assert dummystruct.flags.b
    assert dummystruct.flags.c
