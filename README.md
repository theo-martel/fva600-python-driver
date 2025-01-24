# FVA-600 Python driver

Small drop-in Python driver for the FVA-600 fibered optical attenuator from EXFO (https://www.exfo.com/en/products/field-network-testing/variable-attenuators/FVA-600/).

Reversed-engineered from the C# drivers in the [application](https://apps.exfo.com/en/exfo-apps?platform=FVA-600) written by EXFO

## Requirements
- `crcmod` Python module (https://crcmod.sourceforge.net/). Available in PyPi or Conda forge
- FTD2XX USB driver. Installable from the [publisher's page](https://ftdichip.com/drivers/d2xx-drivers/), and also available with the [EXFO application](https://apps.exfo.com/en/exfo-apps?platform=FVA-600)

## Usage

Loading the driver (with both .py files in the current working directory)
```python
>>> from FVA-600 import FVA600
>>> dev = FVA600()
```

Reading/writing the attenuation value
```python
>>> dev.attenuation
20
>>> dev.attenuation = 10
[A few seconds of processing]
>>> dev.attenuation
10
```

Setting the wavelength used (for attenuation vaue calibration)
```python
>>> dev.wavelength = 1550
```

The driver is directly compatible with contxt manager. Recommended use for long running scripts with possible experimental errors appearing, so that the device will always be left in a safe and controlled state whatever happened during the script
```python 
with FVA600() as dev:
    [long and complex script]
```