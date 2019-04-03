# TES4Py

This is a parser for .esp/.esm files for The Elder Scrolls IV: Oblivion.

With a little modification it should work for Skyrim, Fallout 3, 4 and New Vegas since the format is very similar.

Uses memory-mapped files with memoryview, and lazy parsing for maximum speed.

Came out of an old project (same name) that used `construct3` to parse, but it was too slow when parsing Oblivion.esm

see: https://www.youtube.com/watch?v=w5TLMn5l0g0 for the livestream where I coded this.

This code is _very_ rough.