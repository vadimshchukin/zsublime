# z/OS plugins for the Sublime Text editor

## Overview
This set of plugins for the Sublime Text editor allows to work with different aspects of z/OS: data sets, JCL, JES, HLASM, Endevor SCM. The intent is to work with different text files locally using powerful features of the editor.
The following sections describe each plugin separately.
Only Sublime Text 3 is supported.

## How to install
- [Download and install Sublime Text 3](https://www.sublimetext.com/3).
- [Download the plugins archive](https://github.com/vadimshchukin/zsublime/archive/master.zip).
- Extract the plugins archive to the "%APPDATA%\Sublime Text 3\Packages" folder (can also be opened via "Preferences → Browse Packages" menu item in the editor).
- Configure the settings files of plugins (Endevor/endevor.json and ZFTP/zftp.json) - specify your user ID and optionally your password (if not specified then the plugins will prompt for it every editor's session).
- Use the command palette (Ctrl+Shift+P) to access plugin commands (every command starts with its respective plugin's name).

## Endevor
Features:
- Retrieve element.
- Update element.
- Print element listing.
- Execute SCL.
- Validate sandbox.
- Generate sandbox using SMARTGEN.
- Find load modules containing an object module.
- Compare elements.

## z/FTP
Features:
- Download data set.
- Upload data set.
- Submit job.
- Submit job templated with Jinja2 template engine.
- Print job spool.
- Reconstruct job JCL from JESJCL DD.

## HLASM
Features:
- Basic HLASM syntax highlighting. Enables fast label navigation: Ctrl+P, then "@LABEL".
- Basic HLASM listing syntax highlighting. Enables fast navigation for both labels and offsets: Ctrl+P, then "@LABEL".
- Find the listing line corresponding to a given source line and vice versa.

## JCL
Features:
- Basic syntax highlighting.

## ISPF
Features:
- Pad to width. Pad all selected lines to a given length. Can be useful when editing problem texts for STAR.
- Shift right. Similar to ISPF's shift right command.
- Shift left. Similar to ISPF's shift left command.
