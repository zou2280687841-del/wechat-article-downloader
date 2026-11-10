# Third-party notices

The MIT license in this repository applies to project-owned code only. Third-party components keep their own copyrights and licenses. No third-party source modifications are made by this project.

| Component | Version | License / notice | Upstream |
| --- | --- | --- | --- |
| Python | 3.12 in the supplied Windows build | PSF license | https://www.python.org/ |
| PySide6 / Shiboken6 | 6.8.3 | LGPL-3.0 / GPL / commercial licensing options; this build uses the open-source distribution | https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.8.3 |
| Qt libraries | 6.8.3 | LGPL-3.0 and component-specific licenses | https://code.qt.io/cgit/qt/qtbase.git/tree/?h=v6.8.3 |
| Playwright and bundled driver | 1.65.0 | Apache-2.0; driver includes additional notices | https://github.com/microsoft/playwright-python |
| greenlet | 3.5.6 | MIT / PSF notices | https://github.com/python-greenlet/greenlet |
| openpyxl | 3.1.5 | MIT | https://openpyxl.readthedocs.io/ |
| et-xmlfile | 2.0.0 | MIT | https://foss.heptapod.net/openpyxl/et_xmlfile |
| Beautiful Soup | 4.15.0 | MIT | https://www.crummy.com/software/BeautifulSoup/ |
| Soup Sieve | 4.1 | MIT | https://github.com/facelessuser/soupsieve |
| typing_extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| PyInstaller bootloader | 6.22.3 | GPL with bootloader exception | https://pyinstaller.org/en/stable/license.html |

License texts and notices used for the release are in `docs/licenses/`. Playwright driver notices are included alongside their source attribution there. Microsoft Edge is not redistributed by this project and must be installed separately.

The Windows build uses a directory layout with dynamically loaded Qt libraries in `runtime/_internal/PySide6/`. The project does not prohibit inspection or reverse engineering needed to debug modifications to LGPL-covered components. Corresponding upstream sources for Qt and PySide are available at the version-specific links above. Instructions and complete project source for rebuilding the application are included; replacement libraries must retain a compatible ABI.

The complete Qt 6.8.3 source archive, including additional Qt modules and their component-specific notices, is available from https://download.qt.io/archive/qt/6.8/6.8.3/single/qt-everywhere-src-6.8.3.tar.xz . For the matching PySide / Shiboken source, use the `v6.8.3` upstream source tree linked above. The bundled Python runtime license is in `docs/licenses/Python-LICENSE.txt`.

Qt for Python licensing reference: https://doc.qt.io/qtforpython-6/licenses.html

When rebuilding with different dependencies, refresh this inventory and retain all corresponding component notices.
