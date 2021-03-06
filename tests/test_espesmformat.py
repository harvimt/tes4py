import pytest
from tes4py.espesmformat import *
import contextlib
from pathlib import Path
import mmap
import weakref

def test_accept1():
    esm = EspEsmFormat('E:/HDSteamLib/steamapps/common/Oblivion/data/Oblivion.esm')
    with esm:
        assert esm.header.flags.isesm
        clot_r = next(iter(esm['CLOT'].records))
        for g in esm.groups:
            [r for r in g.records]
        idata = clot_r['DATA'].item_data
        assert idata.gold_value == 8
        assert idata.weight == 4.0
        assert clot_r['FULL'].zstring ==  "Ciirta's Robes"