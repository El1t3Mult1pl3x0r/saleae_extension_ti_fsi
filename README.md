# TI FSI

## Description

The Texas Instruments Fast Serial Interface peripheral/protocol is available on some TI MCUs and MPUs (e.g. AM243x, AM64x).

This high level analyzer decodes the messages from this protocol.

## How to use

1. Create a 'Simple Parallel' analyzer with the clock, d0 and optionally d1 (if used). Clock state should be 'Dual edge'.
1. Create a 'TI FSI' analyzer:
    1. Select the just created Simple Parallel analyzer as the 'Input analyzer'.
    1. Set the 'Amount of data lines used.' to '1' if only D0 data line is used, if also D1 data line is used, set the value to '2'.
    1. When using the 'DATA_N_WORD' frame type in your FSI implementation, set the correct data length in **bytes** (e.g. 16 words = 32 bytes). Otherwise, leave it at the default.

## TODO

* Remove getting started section.

## Getting started

1. Build your extension by updating the Python files for your needs
2. Create a public Github repo and push your code
3. Update this README
4. Open the Logic app and publish your extension
5. Create a Github release
6. Debug your hardware like you've never done before :)
