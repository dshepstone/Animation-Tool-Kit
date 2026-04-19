###############################################################################
# Name:
#   playblast_creator.py
#
# Author:
#   Playblast Creator
#
# Usage:
#   Load as a plugin in Maya
#
# Copyright (C) 2025 Playblast Creator. All rights reserved.
###############################################################################

import datetime
import json
import getpass
import os
import sys

import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as omr
import maya.api.OpenMayaUI as omui

import maya.cmds as cmds

from playblast_creator_presets import PlayblastCreatorShotMaskCustomPresets


def maya_useNewAPI():
    pass


class PlayblastCreatorCmd(om.MPxCommand):

    COMMAND_NAME = "PlayblastCreator"

    PLUG_IN_VERSION = "1.0.1"

    FFMPEG_PATH_ENV_VAR = "PLAYBLAST_CREATOR_FFMPEG"
    TEMP_OUTPUT_DIR_ENV_VAR = "PLAYBLAST_CREATOR_TEMP_OUTPUT_DIR"
    TEMP_FILE_FORMAT_ENV_VAR = "PLAYBLAST_CREATOR_TEMP_FILE_FORMAT"
    LOGO_PATH_ENV_VAR = "PLAYBLAST_CREATOR_LOGO"

    FFMPEG_PATH_OPTION_VAR = "pbcrPlayblastFFmpegPath"
    TEMP_OUTPUT_DIR_OPTION_VAR = "pbcrPlayblastTempOutputPath"
    TEMP_FILE_FORMAT_OPTION_VAR = "pbcrPlayblastTempFileFormat"
    LOGO_PATH_OPTION_VAR = "pbcrShotMaskLogoPath"

    FFMPEG_PATH_FLAG = ["-fp", "-ffmpegPath", om.MSyntax.kString]
    FFMPEG_ENV_VAR_FLAG = ["-fev", "-ffmpegEnvVar"]

    TEMP_OUTPUT_DIR_FLAG = ["-tp", "-tempOutputPath", om.MSyntax.kString]
    TEMP_OUTPUT_ENV_VAR_FLAG = ["-tev", "-tempOutputEnvVar"]

    TEMP_FILE_FORMAT_FLAG = ["-tf", "-tempFileFormat", om.MSyntax.kString]
    TEMP_FILE_FORMAT_ENV_VAR_FLAG = ["-tfe", "-tempFileFormatEnvVar"]

    LOGO_PATH_FLAG = ["-lp", "-logoPath", om.MSyntax.kString]
    LOGO_PATH_ENV_VAR_FLAG = ["-lev", "-logoEnvVar"]

    VERSION_FLAG = ["-v", "-version"]

    TEMP_FILE_FORMATS = [
        "movie",
        "png",
        "tga",
        "tif"
    ]


    def __init__(self):
        """
        """
        super(PlayblastCreatorCmd, self).__init__()

        self.undoable = False

        self.str_values = []

    def doIt(self, arg_list):
        """
        """
        try:
            arg_db = om.MArgDatabase(self.syntax(), arg_list)
        except:
            self.log_error("Error parsing arguments")
            raise

        self.edit = arg_db.isEdit
        self.query = arg_db.isQuery

        self.ffmpeg_path = arg_db.isFlagSet(PlayblastCreatorCmd.FFMPEG_PATH_FLAG[0])
        if self.ffmpeg_path:
            if self.edit:
                self.str_values.append(arg_db.flagArgumentString(PlayblastCreatorCmd.FFMPEG_PATH_FLAG[0], 0))

        self.ffmpeg_env_var = arg_db.isFlagSet(PlayblastCreatorCmd.FFMPEG_ENV_VAR_FLAG[0])

        self.temp_output_dir_path = arg_db.isFlagSet(PlayblastCreatorCmd.TEMP_OUTPUT_DIR_FLAG[0])
        if self.temp_output_dir_path:
            if self.edit:
                self.str_values.append(arg_db.flagArgumentString(PlayblastCreatorCmd.TEMP_OUTPUT_DIR_FLAG[0], 0))

        self.temp_output_env_var = arg_db.isFlagSet(PlayblastCreatorCmd.TEMP_OUTPUT_ENV_VAR_FLAG[0])

        self.temp_file_format = arg_db.isFlagSet(PlayblastCreatorCmd.TEMP_FILE_FORMAT_FLAG[0])
        if self.temp_file_format:
            if self.edit:
                self.str_values.append(arg_db.flagArgumentString(PlayblastCreatorCmd.TEMP_FILE_FORMAT_FLAG[0], 0))

        self.temp_file_format_env_var = arg_db.isFlagSet(PlayblastCreatorCmd.TEMP_FILE_FORMAT_ENV_VAR_FLAG[0])

        self.logo_path = arg_db.isFlagSet(PlayblastCreatorCmd.LOGO_PATH_FLAG[0])
        if self.logo_path:
            if self.edit:
                self.str_values.append(arg_db.flagArgumentString(PlayblastCreatorCmd.LOGO_PATH_FLAG[0], 0))

        self.logo_path_env_var = arg_db.isFlagSet(PlayblastCreatorCmd.LOGO_PATH_ENV_VAR_FLAG[0])

        self.version = arg_db.isFlagSet(PlayblastCreatorCmd.VERSION_FLAG[0])

        self.redoIt()

    def redoIt(self):
        """
        """
        if self.ffmpeg_path:
            if self.edit:
                self.set_ffmpeg_path()
            elif self.query:
                self.get_ffmpeg_path()

        elif self.ffmpeg_env_var:
            self.is_ffmpeg_env_var_set()

        elif self.temp_output_dir_path:
            if self.edit:
                self.set_temp_output_dir_path()
            elif self.query:
                self.get_temp_output_dir_path()

        elif self.temp_output_env_var:
            self.is_temp_output_env_var_set()

        elif self.temp_file_format:
            if self.edit:
                self.set_temp_file_format()
            elif self.query:
                self.get_temp_file_format()

        elif self.temp_file_format_env_var:
            self.is_temp_file_format_env_var_set()

        elif self.logo_path:
            if self.edit:
                self.set_logo_path()
            elif self.query:
                self.get_logo_path()

        elif self.logo_path_env_var:
            self.is_logo_path_env_var_set()

        elif self.version:
            self.get_version()

    def isUndoable(self):
        """
        """
        return self.undoable

    def get_ffmpeg_path(self):
        """
        """
        self.setResult(PlayblastCreatorCmd.resolve_env_var(PlayblastCreatorCmd.FFMPEG_PATH_ENV_VAR, PlayblastCreatorCmd.FFMPEG_PATH_OPTION_VAR))

    def set_ffmpeg_path(self):
        """
        """
        PlayblastCreatorCmd.set_opt_var_str(PlayblastCreatorCmd.FFMPEG_PATH_OPTION_VAR, self.str_values[0])

    def is_ffmpeg_env_var_set(self):
        """
        """
        self.setResult(PlayblastCreatorCmd.is_env_var_set(PlayblastCreatorCmd.FFMPEG_PATH_ENV_VAR))

    def get_temp_output_dir_path(self):
        """
        """
        self.setResult(PlayblastCreatorCmd.resolve_env_var(PlayblastCreatorCmd.TEMP_OUTPUT_DIR_ENV_VAR, PlayblastCreatorCmd.TEMP_OUTPUT_DIR_OPTION_VAR))

    def set_temp_output_dir_path(self):
        """
        """
        PlayblastCreatorCmd.set_opt_var_str(PlayblastCreatorCmd.TEMP_OUTPUT_DIR_OPTION_VAR, self.str_values[0])

    def is_temp_output_env_var_set(self):
        """
        """
        self.setResult(PlayblastCreatorCmd.is_env_var_set(PlayblastCreatorCmd.TEMP_OUTPUT_DIR_ENV_VAR))

    def get_temp_file_format(self):
        """
        """
        temp_file_format = PlayblastCreatorCmd.resolve_env_var(PlayblastCreatorCmd.TEMP_FILE_FORMAT_ENV_VAR, PlayblastCreatorCmd.TEMP_FILE_FORMAT_OPTION_VAR)

        if temp_file_format not in PlayblastCreatorCmd.TEMP_FILE_FORMATS:
            temp_file_format = "png"

        self.setResult(temp_file_format)

    def set_temp_file_format(self):
        if self.str_values[0] not in PlayblastCreatorCmd.TEMP_FILE_FORMATS:
            PlayblastCreatorCmd.log_error("Invalid temp file format. Expected one of: {0}".format(PlayblastCreatorCmd.TEMP_FILE_FORMATS))
            return

        PlayblastCreatorCmd.set_opt_var_str(PlayblastCreatorCmd.TEMP_FILE_FORMAT_OPTION_VAR, self.str_values[0])

    def is_temp_file_format_env_var_set(self):
        self.setResult(PlayblastCreatorCmd.is_env_var_set(PlayblastCreatorCmd.TEMP_FILE_FORMAT_ENV_VAR))

    def get_logo_path(self):
        """
        """
        self.setResult(PlayblastCreatorCmd.resolve_env_var(PlayblastCreatorCmd.LOGO_PATH_ENV_VAR, PlayblastCreatorCmd.LOGO_PATH_OPTION_VAR))

    def set_logo_path(self):
        """
        """
        PlayblastCreatorCmd.set_opt_var_str(PlayblastCreatorCmd.LOGO_PATH_OPTION_VAR, self.str_values[0])

    def is_logo_path_env_var_set(self):
        """
        """
        self.setResult(PlayblastCreatorCmd.is_env_var_set(PlayblastCreatorCmd.LOGO_PATH_ENV_VAR))

    def get_version(self):
        self.setResult(PlayblastCreatorCmd.PLUG_IN_VERSION)

    @classmethod
    def is_env_var_set(cls, name):
        return name in os.environ.keys()

    @classmethod
    def get_env_var_value(cls, name):
        return os.environ.get(name)

    @classmethod
    def get_opt_var_str(cls, name):
        if cmds.optionVar(exists=name):
            return cmds.optionVar(q=name)

        return ""

    @classmethod
    def set_opt_var_str(cls, name, value):
        cmds.optionVar(sv=(name, value))

    @classmethod
    def remove_option_var(cls, name):
        cmds.optionVar(remove=name)

    @classmethod
    def resolve_env_var(cls, env_var_name, opt_var_name):
        if cls.is_env_var_set(env_var_name):
            return cls.get_env_var_value(env_var_name)

        return cls.get_opt_var_str(opt_var_name)

    @classmethod
    def log_error(cls, msg):
        om.MGlobal.displayError("[PlayblastCreator] {0}".format(msg))

    @classmethod
    def creator(cls):
        """
        """
        return PlayblastCreatorCmd()

    @classmethod
    def create_syntax(cls):
        """
        """
        syntax = om.MSyntax()

        syntax.enableEdit = True
        syntax.enableQuery = True

        syntax.addFlag(*cls.FFMPEG_PATH_FLAG)
        syntax.addFlag(*cls.FFMPEG_ENV_VAR_FLAG)
        syntax.addFlag(*cls.TEMP_OUTPUT_DIR_FLAG)
        syntax.addFlag(*cls.TEMP_OUTPUT_ENV_VAR_FLAG)
        syntax.addFlag(*cls.TEMP_FILE_FORMAT_FLAG)
        syntax.addFlag(*cls.TEMP_FILE_FORMAT_ENV_VAR_FLAG)
        syntax.addFlag(*cls.LOGO_PATH_FLAG)
        syntax.addFlag(*cls.LOGO_PATH_ENV_VAR_FLAG)
        syntax.addFlag(*cls.VERSION_FLAG)

        return syntax


class PlayblastCreatorShotMaskLocator(omui.MPxLocatorNode):
    """
    """

    NAME = "PlayblastCreatorShotMask"
    TYPE_ID = om.MTypeId(0x00123456)  # Replace with your unique ID
    DRAW_DB_CLASSIFICATION = "drawdb/geometry/playblast_creatorshotmask"
    DRAW_REGISTRANT_ID = "PlayblastCreatorShotMaskLocator"

    TEXT_ATTRS = ["topLeftText", "tlt", "topCenterText", "tct", "topRightText", "trt",
                  "bottomLeftText", "blt", "bottomCenterText", "bct", "bottomRightText", "brt"]

    def __init__(self):
        """
        """
        super(PlayblastCreatorShotMaskLocator, self).__init__()

    def postConstructor(self):
        """
        """
        node_fn = om.MFnDependencyNode(self.thisMObject())

        node_fn.findPlug("castsShadows", False).setBool(False)
        node_fn.findPlug("receiveShadows", False).setBool(False)
        node_fn.findPlug("motionBlur", False).setBool(False)

    def excludeAsLocator(self):
        """
        """
        return False

    @classmethod
    def creator(cls):
        """
        """
        return PlayblastCreatorShotMaskLocator()

    @classmethod
    def initialize(cls):
        """
        """
        numeric_attr = om.MFnNumericAttribute()
        typed_attr = om.MFnTypedAttribute()
        stringData = om.MFnStringData()

        obj = stringData.create("")
        camera_name = typed_attr.create("camera", "cam", om.MFnData.kString, obj)
        cls.update_attr_properties(typed_attr)
        PlayblastCreatorShotMaskLocator.addAttribute(camera_name)

        for i in range(0, len(cls.TEXT_ATTRS), 2):
            obj = stringData.create("Position {0}".format(str(i / 2 + 1).zfill(2)))
            position = typed_attr.create(cls.TEXT_ATTRS[i], cls.TEXT_ATTRS[i + 1], om.MFnData.kString, obj)
            cls.update_attr_properties(typed_attr)
            PlayblastCreatorShotMaskLocator.addAttribute(position)

        text_padding = numeric_attr.create("textPadding", "tp", om.MFnNumericData.kShort, 10)
        cls.update_attr_properties(numeric_attr)
        numeric_attr.setMin(0)
        numeric_attr.setMax(50)
        PlayblastCreatorShotMaskLocator.addAttribute(text_padding)

        obj = stringData.create("Consolas")
        font_name = typed_attr.create("fontName", "fn", om.MFnData.kString, obj)
        cls.update_attr_properties(typed_attr)
        PlayblastCreatorShotMaskLocator.addAttribute(font_name)

        font_color = numeric_attr.createColor("fontColor", "fc")
        cls.update_attr_properties(numeric_attr)
        numeric_attr.default = (1.0, 1.0, 1.0)
        PlayblastCreatorShotMaskLocator.addAttribute(font_color)

        font_alpha = numeric_attr.create("fontAlpha", "fa", om.MFnNumericData.kFloat, 1.0)
        cls.update_attr_properties(numeric_attr)
        numeric_attr.setMin(0.0)
        numeric_attr.setMax(1.0)
        PlayblastCreatorShotMaskLocator.addAttribute(font_alpha)

        font_scale = numeric_attr.create("fontScale", "fs", om.MFnNumericData.kFloat, 1.0)
        cls.update_attr_properties(numeric_attr)
        numeric_attr.setMin(0.1)
        numeric_attr.setMax(2.0)
        PlayblastCreatorShotMaskLocator.addAttribute(font_scale)

        top_border = numeric_attr.create("topBorder", "tbd", om.MFnNumericData.kBoolean, True)
        cls.update_attr_properties(numeric_attr)
        PlayblastCreatorShotMaskLocator.addAttribute(top_border)

        bottom_border = numeric_attr.create("bottomBorder", "bbd", om.MFnNumericData.kBoolean, True)
        cls.update_attr_properties(numeric_attr)
        PlayblastCreatorShotMaskLocator.addAttribute(bottom_border)

        border_color = numeric_attr.createColor("borderColor", "bc")
        cls.update_attr_properties(numeric_attr)
        numeric_attr.default = (0.0, 0.0, 0.0)
        PlayblastCreatorShotMaskLocator.addAttribute(border_color)

        border_alpha = numeric_attr.create("borderAlpha", "ba", om.MFnNumericData.kFloat, 1.0)
        cls.update_attr_properties(numeric_attr)
        numeric_attr.setMin(0.0)
        numeric_attr.setMax(1.0)
        PlayblastCreatorShotMaskLocator.addAttribute(border_alpha)

        border_scale = numeric_attr.create("borderScale", "bs", om.MFnNumericData.kFloat, 1.0)
        cls.update_attr_properties(numeric_attr)
        numeric_attr.setMin(0.5)
        numeric_attr.setMax(5.0)
        PlayblastCreatorShotMaskLocator.addAttribute(border_scale)

        border_aspect_ratio_enabled = numeric_attr.create("aspectRatioBorders", "arb", om.MFnNumericData.kBoolean, False)
        cls.update_attr_properties(numeric_attr)
        PlayblastCreatorShotMaskLocator.addAttribute(border_aspect_ratio_enabled)

        border_aspect_ratio = numeric_attr.create("borderAspectRatio", "bar", om.MFnNumericData.kFloat, 2.35)
        cls.update_attr_properties(numeric_attr)
        numeric_attr.setMin(0.1)
        numeric_attr.setMax(10.0)
        PlayblastCreatorShotMaskLocator.addAttribute(border_aspect_ratio)

        counter_padding = numeric_attr.create("counterPadding", "cpd", om.MFnNumericData.kShort, 4)
        cls.update_attr_properties(numeric_attr)
        numeric_attr.setMin(1)
        numeric_attr.setMax(6)
        PlayblastCreatorShotMaskLocator.addAttribute(counter_padding)

    @classmethod
    def update_attr_properties(cls, attr):
        attr.writable = True
        attr.storable = True
        if attr.type() == om.MFn.kNumericAttribute:
            attr.keyable = True


class PlayblastCreatorShotMaskData(om.MUserData):
    """
    """

    def __init__(self):
        """
        """
        super(PlayblastCreatorShotMaskData, self).__init__(False)  # don't delete after draw

        self.parsed_fields = []

        self.current_time = 0
        self.counter_padding = 4

        self.font_color = om.MColor((1.0, 1.0, 1.0))
        self.font_scale = 1.0
        self.text_padding = 10

        self.top_border = True
        self.bottom_border = True
        self.border_color = om.MColor((0.0, 0.0, 0.0))

        self.vp_width = 0
        self.vp_height = 0

        self.mask_width = 0
        self.mask_height = 0


class PlayblastCreatorShotMaskDrawOverride(omr.MPxDrawOverride):
    """
    """

    NAME = "playblast_creatorshotmask_draw_override"

    def __init__(self, obj):
        """
        """
        super(PlayblastCreatorShotMaskDrawOverride, self).__init__(obj, PlayblastCreatorShotMaskDrawOverride.draw)

    def supportedDrawAPIs(self):
        """
        """
        return (omr.MRenderer.kAllDevices)

    def hasUIDrawables(self):
        """
        """
        return True

    def prepareForDraw(self, obj_path, camera_path, frame_context, old_data):
        """
        """
        data = old_data
        if not isinstance(data, PlayblastCreatorShotMaskData):
            data = PlayblastCreatorShotMaskData()

        # --- Shot mask attribute values
        dag_fn = om.MFnDagNode(obj_path)

        camera_name = dag_fn.findPlug("camera", False).asString()
        if camera_name and self.camera_exists(camera_name) and not self.is_camera_match(camera_path, camera_name):
            return None

        data.current_time = int(cmds.currentTime(q=True))

        data.counter_padding = dag_fn.findPlug("counterPadding", False).asInt()

        data.text_padding = dag_fn.findPlug("textPadding", False).asInt()

        data.font_name = dag_fn.findPlug("fontName", False).asString()

        r = dag_fn.findPlug("fontColorR", False).asFloat()
        g = dag_fn.findPlug("fontColorG", False).asFloat()
        b = dag_fn.findPlug("fontColorB", False).asFloat()
        a = dag_fn.findPlug("fontAlpha", False).asFloat()
        data.font_color = om.MColor((r, g, b, a))

        data.font_scale = dag_fn.findPlug("fontScale", False).asFloat()

        r = dag_fn.findPlug("borderColorR", False).asFloat()
        g = dag_fn.findPlug("borderColorG", False).asFloat()
        b = dag_fn.findPlug("borderColorB", False).asFloat()
        a = dag_fn.findPlug("borderAlpha", False).asFloat()
        data.border_color = om.MColor((r, g, b, a))

        data.border_scale = dag_fn.findPlug("borderScale", False).asFloat()

        data.top_border = dag_fn.findPlug("topBorder", False).asBool()
        data.bottom_border = dag_fn.findPlug("bottomBorder", False).asBool()

        data.parsed_fields = []
        for i in range(0, len(PlayblastCreatorShotMaskLocator.TEXT_ATTRS), 2):
            parsed_text = self.parse_text(dag_fn.findPlug(PlayblastCreatorShotMaskLocator.TEXT_ATTRS[i], False).asString(), camera_path, data)
            data.parsed_fields.append(parsed_text)

        # --- Shot mask dimension data
        vp_x, vp_y, data.vp_width, data.vp_height = frame_context.getViewportDimensions()  # pylint: disable=W0612
        if not (data.vp_width and data.vp_height):
            return None

        data.mask_width, data.mask_height = self.get_mask_width_height(camera_path, data.vp_width, data.vp_height)
        if not (data.mask_width and data.mask_height):
            return None

        data.mask_aspect_ratio = data.mask_width / data.mask_height
        data.border_aspect_ratio = dag_fn.findPlug("borderAspectRatio", False).asFloat()
        data.aspect_ratio_borders = dag_fn.findPlug("aspectRatioBorders", False).asBool()

        try:
            # This command doesn't exist on macOS
            data.real_scale_value = cmds.mayaDpiSetting(query=True, rsv=True)
        except:
            data.real_scale_value = 1.0

        return data

    def addUIDrawables(self, obj_path, draw_manager, frame_context, data):
        """
        """
        if not (data and isinstance(data, PlayblastCreatorShotMaskData)):
            return

        vp_half_width = 0.5 * data.vp_width
        vp_half_height = 0.5 * data.vp_height

        mask_half_width = 0.5 * data.mask_width
        mask_x = vp_half_width - mask_half_width

        mask_half_height = 0.5 * data.mask_height
        mask_bottom_y = vp_half_height - mask_half_height
        mask_top_y = vp_half_height + mask_half_height

        border_height = int(0.05 * data.mask_height * data.border_scale)

        if data.aspect_ratio_borders:
            border_aspect_ratio_height = data.mask_width / data.border_aspect_ratio
            aspect_ratio_border_height = int(0.5 * (data.mask_height - border_aspect_ratio_height))

            if(aspect_ratio_border_height > 0):
                border_height = aspect_ratio_border_height
            else:
                om.MGlobal.displayWarning("Border aspect ratio ({0}) <= mask aspect ratio ({1}). Reverting to border scale mode.".format(round(data.border_aspect_ratio, 3), round(data.mask_aspect_ratio, 3)))


        font_size = int((border_height - border_height * 0.15) * data.font_scale / data.real_scale_value)
        background_size = (int(data.mask_width), border_height)

        draw_manager.beginDrawable()
        draw_manager.setFontName(data.font_name)
        draw_manager.setColor(data.font_color)

        if data.top_border:
            self.draw_border(draw_manager, om.MPoint(mask_x, mask_top_y - border_height, 0.1), background_size, data.border_color)
        if data.bottom_border:
            self.draw_border(draw_manager, om.MPoint(mask_x, mask_bottom_y, 0.1), background_size, data.border_color)

        self.draw_label(draw_manager, om.MPoint(mask_x + data.text_padding, mask_top_y - border_height, 0.0), data, 0, omr.MUIDrawManager.kLeft, font_size, background_size)
        self.draw_label(draw_manager, om.MPoint(vp_half_width, mask_top_y - border_height, 0.0), data, 1, omr.MUIDrawManager.kCenter, font_size, background_size)
        self.draw_label(draw_manager, om.MPoint(mask_x + data.mask_width - data.text_padding, mask_top_y - border_height, 0.0), data, 2, omr.MUIDrawManager.kRight, font_size, background_size)
        self.draw_label(draw_manager, om.MPoint(mask_x + data.text_padding, mask_bottom_y, 0.0), data, 3, omr.MUIDrawManager.kLeft, font_size, background_size)
        self.draw_label(draw_manager, om.MPoint(vp_half_width, mask_bottom_y, 0.0), data, 4, omr.MUIDrawManager.kCenter, font_size, background_size)
        self.draw_label(draw_manager, om.MPoint(mask_x + data.mask_width - data.text_padding, mask_bottom_y, 0.0), data, 5, omr.MUIDrawManager.kRight, font_size, background_size)

        draw_manager.endDrawable()

    def get_mask_width_height(self, camera_path, vp_width, vp_height):
        """
        """
        camera_fn = om.MFnCamera(camera_path)

        camera_aspect_ratio = camera_fn.aspectRatio()
        device_aspect_ratio = cmds.getAttr("defaultResolution.deviceAspectRatio")
        vp_aspect_ratio = vp_width / float(vp_height)

        scale = 1.0

        if camera_fn.filmFit == om.MFnCamera.kHorizontalFilmFit:
            mask_width = vp_width / camera_fn.overscan
            mask_height = mask_width / device_aspect_ratio
        elif camera_fn.filmFit == om.MFnCamera.kVerticalFilmFit:
            mask_height = vp_height / camera_fn.overscan
            mask_width = mask_height * device_aspect_ratio
        elif camera_fn.filmFit == om.MFnCamera.kFillFilmFit:
            if vp_aspect_ratio < camera_aspect_ratio:
                if camera_aspect_ratio < device_aspect_ratio:
                    scale = camera_aspect_ratio / vp_aspect_ratio
                else:
                    scale = device_aspect_ratio / vp_aspect_ratio
            elif camera_aspect_ratio > device_aspect_ratio:
                scale = device_aspect_ratio / camera_aspect_ratio

            mask_width = vp_width / camera_fn.overscan * scale
            mask_height = mask_width / device_aspect_ratio

        elif camera_fn.filmFit == om.MFnCamera.kOverscanFilmFit:
            if vp_aspect_ratio < camera_aspect_ratio:
                if camera_aspect_ratio < device_aspect_ratio:
                    scale = camera_aspect_ratio / vp_aspect_ratio
                else:
                    scale = device_aspect_ratio / vp_aspect_ratio
            elif camera_aspect_ratio > device_aspect_ratio:
                scale = device_aspect_ratio / camera_aspect_ratio

            mask_height = vp_height / camera_fn.overscan / scale
            mask_width = mask_height * device_aspect_ratio
        else:
            om.MGlobal.displayError("[PlayblastCreatorShotMask] Unsupported Film Fit value")
            return None, None

        return mask_width, mask_height

    def draw_border(self, draw_manager, position, background_size, color):
        """
        """
        draw_manager.text2d(position, " ", alignment=omr.MUIDrawManager.kLeft, backgroundSize=background_size, backgroundColor=color)

    def draw_label(self, draw_manager, position, data, data_index, alignment, font_size, background_size):
        """
        """
        if data.parsed_fields[data_index]["image_path"]:
            self.draw_image(draw_manager, position, data, data_index, alignment, background_size)
            return


        draw_manager.setColor(data.font_color)

        text = data.parsed_fields[data_index]["text"]
        if text:
            if '|' in text:
                split_text = text.split('|', 1)

                half_font_size = int(font_size * 0.5)
                draw_manager.setFontSize(half_font_size)

                top_position = om.MPoint(position)
                top_position.y = top_position.y + int(0.6 * half_font_size * data.real_scale_value)
                draw_manager.text2d(top_position, split_text[0], alignment=alignment, backgroundSize=background_size, backgroundColor=om.MColor((0.0, 0.0, 0.0, 0.0)))

                bottom_position = om.MPoint(position)
                bottom_position.y = bottom_position.y - int(0.5 * half_font_size * data.real_scale_value)
                draw_manager.text2d(bottom_position, split_text[1], alignment=alignment, backgroundSize=background_size, backgroundColor=om.MColor((0.0, 0.0, 0.0, 0.0)))

            else:
                draw_manager.setFontSize(font_size)
                draw_manager.text2d(position, text, alignment=alignment, backgroundSize=background_size, backgroundColor=om.MColor((0.0, 0.0, 0.0, 0.0)))

    def draw_image(self, draw_manager, position, data, data_index, alignment, background_size):
        """
        """
        texture_manager = omr.MRenderer.getTextureManager()
        texture = texture_manager.acquireTexture(data.parsed_fields[data_index]["image_path"])
        if not texture:
            om.MGlobal.displayError("[PlayblastCreatorShotMask] Unsupported image file: {0}".format(data.image_paths[data_index]))
            return

        draw_manager.setTexture(texture)
        draw_manager.setTextureSampler(omr.MSamplerState.kMinMagMipLinear, omr.MSamplerState.kTexClamp)
        draw_manager.setTextureMask(omr.MBlendState.kRGBAChannels)
        draw_manager.setColor(om.MColor((1.0, 1.0, 1.0, data.font_color.a)))

        # Scale the image based on the border height
        texture_desc = texture.textureDescription()
        scale_y = (0.5 * background_size[1]) - 4
        scale_x = scale_y / texture_desc.fHeight * texture_desc.fWidth

        if alignment == omr.MUIDrawManager.kLeft:
            position = om.MPoint(position.x + scale_x, position.y + int(0.5 * background_size[1]))
        elif alignment == omr.MUIDrawManager.kRight:
            position = om.MPoint(position.x - scale_x, position.y + int(0.5 * background_size[1]))
        else:
            position = om.MPoint(position.x, position.y + int(0.5 * background_size[1]))

        draw_manager.rect2d(position, om.MVector(0.0, 1.0, 0.0), scale_x, scale_y, True)

    def camera_exists(self, name):
        """
        """
        dg_iter = om.MItDependencyNodes(om.MFn.kCamera)
        while not dg_iter.isDone():
            if dg_iter.thisNode().hasFn(om.MFn.kDagNode):
                camera_path = om.MDagPath.getAPathTo(dg_iter.thisNode())
                if self.is_camera_match(camera_path, name):
                    return True
            dg_iter.next()

        return False

    def is_camera_match(self, camera_path, name):
        """
        """
        if self.camera_transform_name(camera_path) == name or self.camera_shape_name(camera_path) == name:
            return True

        return False

    def camera_transform_name(self, camera_path):
        """
        """
        camera_transform = camera_path.transform()
        if camera_transform:
            return om.MFnTransform(camera_transform).name()

        return ""

    def camera_shape_name(self, camera_path):
        """
        """
        camera_shape = camera_path.node()
        if camera_shape:
            return om.MFnCamera(camera_shape).name()

        return ""

    def get_scene_name(self):
        scene_name = cmds.file(q=True, sceneName=True, shortName=True)
        if scene_name:
            scene_name = os.path.splitext(scene_name)[0]
        else:
            scene_name = "untitled"

        return scene_name

    def get_focal_length(self, camera_path):
        camera = om.MFnCamera(camera_path)
        return "{0}".format(int(round(camera.focalLength)))

    def get_username(self):
        return getpass.getuser()

    def get_date(self):
        """
        """
        return datetime.date.today().strftime('%Y/%m/%d')

    def get_image(self, image_path):
        """
        """
        image_path = image_path.strip()
        if os.path.exists(image_path):
            return image_path, ""

        return "", "Image not found"

    def parse_text(self, orig_text, camera_path, data):
        """
        """
        label = ""
        image_path = ""

        text = orig_text
        text = PlayblastCreatorShotMaskCustomPresets.parse_shot_mask_text(text)

        if "{counter}" in text:
            text = text.replace("{counter}", "{0}".format(str(data.current_time).zfill(data.counter_padding)))
        if "{scene}" in text:
            text = text.replace("{scene}", "{0}".format(self.get_scene_name()))
        if "{camera}" in text:
            text = text.replace("{camera}", "{0}".format(self.camera_transform_name(camera_path)))
        if "{focal_length}" in text:
            text = text.replace("{focal_length}", "{0}".format(self.get_focal_length(camera_path)))
        if "{fps}" in text:
            text = text.replace("{fps}", "{0}".format(cmds.currentUnit(q=True, time=True)))
        if "{shot}" in text:
            text = text.replace("{shot}", "001")
        if "{username}" in text:
            text = text.replace("{username}", "{0}".format(self.get_username()))
        if "{date}" in text:
            text = text.replace("{date}", "{0}".format(self.get_date()))

        stripped_text = text.strip()
        if stripped_text.startswith("{logo}"):
            logo_path = PlayblastCreatorCmd.resolve_env_var(PlayblastCreatorCmd.LOGO_PATH_ENV_VAR, PlayblastCreatorCmd.LOGO_PATH_OPTION_VAR)
            image_path, text = self.get_image(logo_path)

        if stripped_text.startswith("{image=") and stripped_text.endswith("}"):
            image_path, text = self.get_image(stripped_text[7:-1])

        return {"label": label, "text": text, "image_path": image_path}

    @staticmethod
    def creator(obj):
        """
        """
        return PlayblastCreatorShotMaskDrawOverride(obj)

    @staticmethod
    def draw(context, data):
        """
        """
        return


def initializePlugin(obj):
    """
    """
    plugin_fn = om.MFnPlugin(obj, "Playblast Creator", PlayblastCreatorCmd.PLUG_IN_VERSION, "Any")

    try:
        plugin_fn.registerCommand(PlayblastCreatorCmd.COMMAND_NAME, PlayblastCreatorCmd.creator, PlayblastCreatorCmd.create_syntax)
    except:
        om.MGlobal.displayError("Failed to register command: {0}".format(PlayblastCreatorCmd.COMMAND_NAME))

    try:
        plugin_fn.registerNode(PlayblastCreatorShotMaskLocator.NAME,
                               PlayblastCreatorShotMaskLocator.TYPE_ID,
                               PlayblastCreatorShotMaskLocator.creator,
                               PlayblastCreatorShotMaskLocator.initialize,
                               om.MPxNode.kLocatorNode,
                               PlayblastCreatorShotMaskLocator.DRAW_DB_CLASSIFICATION)
    except:
        om.MGlobal.displayError("Failed to register node: {0}".format(PlayblastCreatorShotMaskLocator.NAME))

    try:
        omr.MDrawRegistry.registerDrawOverrideCreator(PlayblastCreatorShotMaskLocator.DRAW_DB_CLASSIFICATION,
                                                      PlayblastCreatorShotMaskLocator.DRAW_REGISTRANT_ID,
                                                      PlayblastCreatorShotMaskDrawOverride.creator)
    except:
        om.MGlobal.displayError("Failed to register draw override: {0}".format(PlayblastCreatorShotMaskDrawOverride.NAME))


def uninitializePlugin(obj):
    """
    """
    plugin_fn = om.MFnPlugin(obj)

    try:
        omr.MDrawRegistry.deregisterDrawOverrideCreator(PlayblastCreatorShotMaskLocator.DRAW_DB_CLASSIFICATION, PlayblastCreatorShotMaskLocator.DRAW_REGISTRANT_ID)
    except:
        om.MGlobal.displayError("Failed to deregister draw override: {0}".format(PlayblastCreatorShotMaskDrawOverride.NAME))

    try:
        plugin_fn.deregisterNode(PlayblastCreatorShotMaskLocator.TYPE_ID)
    except:
        om.MGlobal.displayError("Failed to unregister node: {0}".format(PlayblastCreatorShotMaskLocator.NAME))

    try:
        plugin_fn.deregisterCommand(PlayblastCreatorCmd.COMMAND_NAME)
    except:
        om.MGlobal.displayError("Failed to deregister command: {0}".format(PlayblastCreatorCmd.COMMAND_NAME))


if __name__ == "__main__":

    cmds.file(f=True, new=True)

    plugin_name = "playblast_creator.py"
    cmds.evalDeferred('if cmds.pluginInfo("{0}", q=True, loaded=True): cmds.unloadPlugin("{0}")'.format(plugin_name))
    cmds.evalDeferred('if not cmds.pluginInfo("{0}", q=True, loaded=True): cmds.loadPlugin("{0}")'.format(plugin_name))

    cmds.evalDeferred('cmds.createNode("PlayblastCreatorShotMask")')
