###############################################################################
# Name:
#   playblast_creator_presets.py
#
# Author:
#   Playblast Creator
#
# Usage:
#   Customizable presets for Playblast Creator Tool
#
# Copyright (C) 2025 Playblast Creator. All rights reserved.
###############################################################################

class PlayblastCreatorCustomPresets(object):


    RESOLUTION_PRESETS = [
        #
        # Format:  ["preset_name", (width, height)],
        #

        ["HD 1080", (1920, 1080)],
        ["HD 720", (1280, 720)],
        ["HD 540", (960, 540)],
        ["4K UHD", (3840, 2160)],
    ]


    VIEWPORT_VISIBILITY_PRESETS = [
        #
        # Format: ["preset_name", ["type_name_1", "type_name_2", ...]],
        #
        # Viewport visibility types:
        #
        #    Controllers            NURBS Curves      NURBS Surfaces          NURBS CVs
        #    NURBS Hulls            Polygons          Subdiv Surfaces         Planes
        #    Lights                 Cameras           Image Planes            Joints
        #    IK Handles             Deformers         Dynamics                Particle Instancers
        #    Fluids                 Hair Systems      Follicles               nCloths
        #    nParticles             nRigids           Dynamic Constraints     Locators
        #    Dimensions             Pivots            Handles                 Texture Placements
        #    Strokes                Motion Trails     Plugin Shapes           Clip Ghosts
        #    Grease Pencil          Grid              HUD                     Hold-Outs
        #    Selection Highlighting
        #

        ["Geo", ["NURBS Surfaces", "Polygons"]],
        ["Dynamics", ["NURBS Surfaces", "Polygons", "Dynamics", "Fluids", "nParticles"]],
        ["Animation", ["NURBS Surfaces", "Polygons", "Joints", "IK Handles", "Deformers"]],
    ]

    PLAYBLAST_OUTPUT_PATH_LOOKUP = [
        #
        # Format:  ("display_name", "{tag_name}"),
        #
        ("Playblast Creator Projects", "{playblast_creator_projects}"),
    ]

    PLAYBLAST_OUTPUT_FILENAME_LOOKUP = [
        #
        # Format:  ("display_name", "{tag_name}"),
        #
        ("Student ID", "{student_id}"),
        ("Course Code", "{course_code}"),
    ]


    @classmethod
    def parse_playblast_output_dir_path(cls, dir_path):
        """
        User defined output directory {tags}. Logic should replace tag with a string.

        PLAYBLAST_OUTPUT_PATH_LOOKUP can be used to add {tag} to context menu.
        """
        if "{playblast_creator_projects}" in dir_path:
            # Replace with your desired path or environment variable
            playblast_creator_projects_path = "C:/Playblast CreatorProjects"
            dir_path = dir_path.replace("{playblast_creator_projects}", playblast_creator_projects_path)

        return dir_path

    @classmethod
    def parse_playblast_output_filename(cls, filename):
        """
        User defined output filenname {tags}. Logic should replace tag with a string.

        PLAYBLAST_OUTPUT_FILENAME_LOOKUP can be used to add {tag} to context menu.
        """
        if "{student_id}" in filename:
            # This could be retrieved from an environment variable or configuration file
            student_id = "0000000"  # Default value
            filename = filename.replace("{student_id}", student_id)
            
        if "{course_code}" in filename:
            # This could be retrieved from an environment variable or configuration file
            course_code = "ANIM0000"  # Default value
            filename = filename.replace("{course_code}", course_code)

        return filename


class PlayblastCreatorShotMaskCustomPresets(object):


    SHOT_MASK_LABEL_LOOKUP = [
        #
        # Format:  ("display_name", "{tag_name}"),
        #
        ("Student ID", "{student_id}"),
        ("Course Code", "{course_code}"),
        ("Assignment", "{assignment}"),
    ]

    @classmethod
    def parse_shot_mask_text(cls, text):
        """
        User defined shot mask label {tags}. Logic should replace tag with a string.

        SHOT_MASK_LABEL_LOOKUP can be used to add {tag} to context menu.
        """
        if "{student_id}" in text:
            # This could be retrieved from an environment variable or configuration file
            student_id = "0000000"  # Default value
            text = text.replace("{student_id}", student_id)
            
        if "{course_code}" in text:
            # This could be retrieved from an environment variable or configuration file
            course_code = "ANIM0000"  # Default value
            text = text.replace("{course_code}", course_code)
            
        if "{assignment}" in text:
            # This could be retrieved from an environment variable or configuration file
            assignment = "Assignment 1"  # Default value
            text = text.replace("{assignment}", assignment)

        return text
