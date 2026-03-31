# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'BaseSaveWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.8.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_Form(object):
    def setupUi(self, Form):
        if not Form.objectName():
            Form.setObjectName(u"Form")
        Form.resize(167, 473)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Form.sizePolicy().hasHeightForWidth())
        Form.setSizePolicy(sizePolicy)
        Form.setMinimumSize(QSize(160, 0))
        Form.setMaximumSize(QSize(16777215, 16777215))
        Form.setStyleSheet(u"")
        self.verticalLayout = QVBoxLayout(Form)
        self.verticalLayout.setSpacing(4)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.titleFrame = QFrame(Form)
        self.titleFrame.setObjectName(u"titleFrame")
        self.titleFrame.setMinimumSize(QSize(0, 24))
        self.titleFrame.setFrameShape(QFrame.StyledPanel)
        self.titleFrame.setFrameShadow(QFrame.Raised)
        self.verticalLayout_5 = QVBoxLayout(self.titleFrame)
        self.verticalLayout_5.setSpacing(0)
        self.verticalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")

        self.verticalLayout.addWidget(self.titleFrame)

        self.thumbnailLayout = QHBoxLayout()
        self.thumbnailLayout.setSpacing(0)
        self.thumbnailLayout.setObjectName(u"thumbnailLayout")
        self.thumbnailLayout.setContentsMargins(-1, 0, -1, 0)
        self.thumbnailFrame = QFrame(Form)
        self.thumbnailFrame.setObjectName(u"thumbnailFrame")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.thumbnailFrame.sizePolicy().hasHeightForWidth())
        self.thumbnailFrame.setSizePolicy(sizePolicy1)
        self.thumbnailFrame.setMinimumSize(QSize(50, 150))
        self.thumbnailFrame.setMaximumSize(QSize(150, 150))
        self.thumbnailFrame.setStyleSheet(u"")
        self.thumbnailFrame.setFrameShape(QFrame.NoFrame)
        self.thumbnailFrame.setFrameShadow(QFrame.Plain)
        self.thumbnailFrame.setLineWidth(0)
        self.verticalLayout_3 = QVBoxLayout(self.thumbnailFrame)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(0, 2, 0, 2)

        self.thumbnailLayout.addWidget(self.thumbnailFrame)


        self.verticalLayout.addLayout(self.thumbnailLayout)

        self.optionsFrame = QFrame(Form)
        self.optionsFrame.setObjectName(u"optionsFrame")
        self.optionsFrame.setMinimumSize(QSize(0, 16))
        self.optionsFrame.setFrameShape(QFrame.NoFrame)
        self.optionsFrame.setFrameShadow(QFrame.Plain)
        self.optionsFrame.setLineWidth(0)
        self.verticalLayout_4 = QVBoxLayout(self.optionsFrame)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(4, 2, 4, 2)

        self.verticalLayout.addWidget(self.optionsFrame)

        self.previewButtons = QFrame(Form)
        self.previewButtons.setObjectName(u"previewButtons")
        self.previewButtons.setFrameShape(QFrame.NoFrame)
        self.previewButtons.setFrameShadow(QFrame.Plain)
        self.previewButtons.setLineWidth(0)
        self.horizontalLayout_6 = QHBoxLayout(self.previewButtons)
        self.horizontalLayout_6.setSpacing(0)
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_6.addItem(self.horizontalSpacer_3)

        self.acceptButton = QPushButton(self.previewButtons)
        self.acceptButton.setObjectName(u"acceptButton")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.acceptButton.sizePolicy().hasHeightForWidth())
        self.acceptButton.setSizePolicy(sizePolicy2)
        self.acceptButton.setMinimumSize(QSize(80, 35))
        self.acceptButton.setMaximumSize(QSize(140, 35))
        font = QFont()
        font.setFamilies([u"Arial"])
        font.setPointSize(12)
        font.setBold(False)
        self.acceptButton.setFont(font)
        self.acceptButton.setStyleSheet(u"")

        self.horizontalLayout_6.addWidget(self.acceptButton)

        self.selectionSetButton = QPushButton(self.previewButtons)
        self.selectionSetButton.setObjectName(u"selectionSetButton")
        self.selectionSetButton.setMinimumSize(QSize(35, 35))
        self.selectionSetButton.setMaximumSize(QSize(5, 16777215))
        icon = QIcon()
        icon.addFile(u"icons/selectionSet2.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.selectionSetButton.setIcon(icon)
        self.selectionSetButton.setIconSize(QSize(25, 25))

        self.horizontalLayout_6.addWidget(self.selectionSetButton)

        self.horizontalSpacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_6.addItem(self.horizontalSpacer_4)


        self.verticalLayout.addWidget(self.previewButtons)

        self.frame = QFrame(Form)
        self.frame.setObjectName(u"frame")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(2)
        sizePolicy3.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy3)
        self.frame.setFrameShape(QFrame.NoFrame)
        self.frame.setFrameShadow(QFrame.Plain)

        self.verticalLayout.addWidget(self.frame)


        self.retranslateUi(Form)

        QMetaObject.connectSlotsByName(Form)
    # setupUi

    def retranslateUi(self, Form):
        Form.setWindowTitle(QCoreApplication.translate("Form", u"Create Item", None))
#if QT_CONFIG(tooltip)
        self.acceptButton.setToolTip("")
#endif // QT_CONFIG(tooltip)
        self.acceptButton.setText(QCoreApplication.translate("Form", u"Save", None))
        self.selectionSetButton.setText("")
    # retranslateUi

