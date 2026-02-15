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
    1. If you want to copy the data later, you can set the 'Print data to Terminal?' option to 'Yes'. The FSI data is then printed to the Saleae terminal when the 'Stream to terminal' option is also enabled.

### Noteworthy

* Corrupt frames are printed to the terminal, the analyzer should recover with the next frame.
* CRC failures are printed to the terminal and do not break analyzing frames.
