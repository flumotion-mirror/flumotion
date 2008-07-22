# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Flumotion - a streaming media server
# Copyright (C) 2008 Fluendo, S.L. (www.fluendo.com).
# All rights reserved.

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE.GPL" in the source distribution for more information.

# Licensees having purchased or holding a valid Flumotion Advanced
# Streaming Server license may use this file in accordance with the
# Flumotion Advanced Streaming Server Commercial License Agreement.
# See "LICENSE.Flumotion" in the source distribution for more information.

# Headers in this file shall remain intact.

"""File Selector widget and dialog

The widgets in here are in concept similar to FileChooserDialog with the
main difference that it can display remote files over the
twisted.spread/PB protocol.

"""

import gettext
import os

import gtk
from gtk import gdk
from kiwi.ui.objectlist import ObjectList, Column
from kiwi.utils import gsignal

from flumotion.common.errors import AccessDeniedError
from flumotion.common.interfaces import IDirectory, IFile
from flumotion.common.vfs import listDirectory

_ = gettext.gettext


class _File(object):
    def __init__(self, fileInfo, icon):
        self._fileinfo = fileInfo
        self.filename = fileInfo.filename
        self.icon = icon

    def getPath(self):
        return self._fileInfo.getPath()


class FileSelector(ObjectList):
    """I am a widget which can be embedded to display a file selector
    dialog.
    """

    gsignal('selected', object)
    def __init__(self, parent, adminModel):
        """Creates a new FileSelector
        @param parent: parent window
        @type parent: gtk.Window or None
        @param adminModel: the admin model
        @type adminModel: L{AdminModel}
        """
        ObjectList.__init__(self,
                            [Column("icon", title=' ',
                                    data_type=gdk.Pixbuf),
                             Column("filename", expand=True),
                             ])
        self.connect('row-activated', self._on__row_activated)
        self.set_size_request(400, 300)

        self._adminModel = adminModel
        self._parent = parent
        self._workerName = None
        self._iconTheme = gtk.icon_theme_get_default()

    def _rowActivated(self, vfsFile):
        print 'row activated', vfsFile
        if IDirectory.providedBy(vfsFile):
            self.setDirectory(vfsFile.getPath())
        elif IFile.providedBy(vfsFile):
            self.emit('selected', vfsFile)

    def _renderIcon(self, iconNames):
        iconInfo = self._iconTheme.choose_icon(iconNames,
                                               gtk.ICON_SIZE_MENU,
                                               gtk.ICON_LOOKUP_USE_BUILTIN)
        return iconInfo.load_icon()

    def _populateList(self, vfsFiles):
        self.clear()
        for vfsFile in vfsFiles:
            icon = self._renderIcon(vfsFile.iconNames)
            self.append(_File(vfsFile, icon))

    # Callbacks

    def _listingDoneCallback(self, vfsFile):
        d = vfsFile.getFiles()
        d.addCallback(self._gotFilesCallback)
        d.addErrback(self._accessDeniedErrback, vfsFile.getPath())

    def _accessDeniedErrback(self, failure, path):
        failure.trap(AccessDeniedError)
        self.showErrorMessage(failure, self._parent)

    def _gotFilesCallback(self, vfsFiles):
        vfsFiles.sort(cmp=lambda a, b: cmp(a.filename, b.filename))
        self._populateList(vfsFiles)

    def _on__row_activated(self, objectList, vfsFile):
        self._rowActivated(vfsFile)

    # Public API

    def setDirectory(self, path):
        """Change directory of the file chooser
        @param path: the path to show in the file selector
        @type path: str
        """
        d = self._adminModel.workerCallRemote(
            self._workerName,
            'listDirectory', path)
        d.addCallback(self._listingDoneCallback)
        d.addErrback(self._accessDeniedErrback, path)
        return d

    def setWorkerName(self, workerName):
        """Sets the worker name of the file chooser,
        the worker is where the directory structure will
        be shown.
        @param workerName:
        @type workerName:
        """
        self._workerName = workerName


class FileSelectorDialog(gtk.Dialog):
    """I am a dialog which contains a file selector dialog
    """
    def __init__(self, parent, adminModel):
        """Creates a new RemoteFileSelectorDialog
        @param parent: parent window
        @type parent: gtk.Window or None
        @param adminModel: the admin model
        @type adminModel: L{AdminModel}
        """
        gtk.Dialog.__init__(self, _('Select a folder...'),
                            parent, gtk.DIALOG_MODAL)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CANCEL)
        self.add_button(gtk.STOCK_OPEN, gtk.RESPONSE_OK)

        self.selector = FileSelector(parent, adminModel)
        self.vbox.add(self.selector)
        self.selector.show()

    def getFilename(self):
        """Returns the currently selected filename
        @returns: the selected filename
        @rtype: str
        """
        vfsFile = self.selector.get_selected()
        return os.path.abspath(vfsFile.getPath())

    def setDirectory(self, path):
        """Change directory of the file chooser
        @param path: the path to show in the file selector
        @type path: str
        """
        return self.selector.setDirectory(path)