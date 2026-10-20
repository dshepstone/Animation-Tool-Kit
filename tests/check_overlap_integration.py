"""Maya/Qt integration check using a disposable installed-layout directory.

Run from the repo root with mayapy. No artist scripts/preferences are installed.
The new MEL package-copy block is executed against the temporary scripts folder.
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext

root=Path(__file__).resolve().parents[1]
from PySide6 import QtWidgets, QtCore
app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds, mel
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin


def main():
    scratch=root/'work'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(scratch)) as temp:
        scripts=Path(temp)/'scripts'
        icons=Path(temp)/'icons'
        scripts.mkdir()
        icons.mkdir()
        shutil.copytree(root/'atk_toolbar',scripts/'atk_toolbar',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        installer=(root/'install_atk_toolbar.mel').read_text(encoding='utf-8')
        declarations=installer.rsplit('atk__install();',1)[0]
        mel.eval(declarations)
        begin=installer.index('    // Overlap ships as an isolated ATK package')
        end=installer.index('    // Playblast Creator v2.0.4',begin)
        tools=(root/'animation tool kit scripts').as_posix()+'/'
        mel.eval('string $toolsBase = "'+tools+'"; string $scriptsDir = "'+scripts.as_posix()+'/";\n'+installer[begin:end])
        installed=scripts/'atk_overlap'
        assert (installed/'resources/help.html').is_file()
        assert (installed/'LICENSE').is_file()
        shutil.copyfile(installed/'assets/overlap_32.png',icons/'overlap_32.png')
        sys.path.insert(0,str(scripts))
        original_internal=cmds.internalVar
        def internal(**kwargs):
            if kwargs.get('userScriptDir'):
                return str(scripts)+os.sep
            if kwargs.get('userBitmapsDir'):
                return str(icons)+os.sep
            return original_internal(**kwargs)
        with patch.object(cmds,'internalVar',side_effect=internal), patch.object(
                MayaQWidgetDockableMixin,'setVisible',QtWidgets.QDialog.setVisible):
            from atk_toolbar import atk_loader, atk_toolbar, atk_icons
            atk_loader.setup_paths()
            entries=[t for t in atk_loader.TOOL_REGISTRY if t['id']=='overlap']
            assert len(entries)==1 and entries[0]['module']=='atk_overlap'
            assert atk_loader.is_tool_installed('overlap')
            assert atk_loader.is_tool_visible('overlap')
            atk_loader.set_tool_visible('overlap',False)
            assert not atk_loader.is_tool_visible('overlap')
            atk_loader.set_tool_visible('overlap',True)
            import atk_overlap
            import atk_overlap.ui as ui
            def show_without_workspace(self,*args,**kwargs):
                return QtWidgets.QDialog.show(self)
            # Only the workspaceControl boundary needs an interactive Maya UI;
            # the actual registered launcher, Qt window, menus, and solver run.
            with patch.object(ui.Window,'show',show_without_workspace), patch.object(atk_loader,'_watch_launch',nullcontext):
                atk_loader.launch_tool('overlap')
            window=ui._window
            assert window is not None and window.objectName()=='ATKOverlapWindow' and window.isVisible()
            assert [a.text() for a in window.menu_bar.actions()]==['File','Help']
            control=cmds.createNode('transform',name='overlap_test_CTRL')
            for frame,value in ((1,0),(8,4),(16,-2),(24,0)):
                cmds.setKeyframe(control,attribute='tz',time=frame,value=value)
            window.panel.load_controls([control])
            window.panel.axis.setCurrentText('-Y')
            for axis,check in window.panel.channel_checks.items():
                check.setChecked(axis=='X')
            window.panel.start.setValue(1)
            window.panel.end.setValue(24)
            # A key outside the range must survive; one inside is replaced.
            cmds.setKeyframe(control,attribute='rx',time=30,value=7)
            window.panel.make_preview(True)
            assert cmds.ls('Overlap_preview*') and not cmds.ls('Kinequill*')
            assert window.panel.optimize_bake.isChecked()
            window.panel.bake()
            # The bake is a plain time curve on the control: no layer, blend
            # node, preview or endpoint is left connected to or near the rig.
            assert not cmds.ls(type='animLayer')
            sources=cmds.listConnections(control+'.rx',source=True,destination=False) or []
            assert len(sources)==1 and cmds.nodeType(sources[0])=='animCurveTA',sources
            assert (cmds.listConnections(sources[0],source=True,destination=False) or [])==[]
            assert not cmds.ls('Overlap_*') and not cmds.ls('Kinequill*')
            times=cmds.keyframe(control,attribute='rx',query=True,timeChange=True)
            assert 30 in times and min(times)==1 and max(t for t in times if t<30)==24,times
            stats=window.panel.session.last_bake_stats
            assert stats['after']<stats['before'],stats
            assert window.panel.bake_layers.currentData() is None
            cmds.undo()
            assert cmds.keyframe(control,attribute='rx',query=True,timeChange=True)==[30.0]
            # Layers baked by 0.4.0 are refused as input and can be deleted.
            layer=cmds.animLayer('Kinequill_overlap#',override=True)
            cmds.addAttr(layer,longName='overlapBake',attributeType='bool',defaultValue=True)
            cmds.animLayer(layer,edit=True,attribute=control+'.rx')
            window.panel.refresh_bake_layers()
            assert window.panel.bake_layers.currentData()==layer
            window.panel.make_preview(True)
            try:
                window.panel.bake()
                raise AssertionError('Layered channel must be refused')
            except ValueError as error:
                assert 'animation layers' in str(error)
            window.panel.delete_selected_bake()
            assert not cmds.objExists(layer) and cmds.objExists(control)
            assert not atk_icons._generate_icon('overlap','timing',32).isNull()
            # Verify registry-driven button creation and click dispatch.
            with patch.object(atk_toolbar.ATKToolbarWidget,'_add_inbetweener_slider'), patch.object(atk_toolbar,'_show_frame_stepper',return_value=False):
                toolbar=atk_toolbar.ATKToolbarWidget()
            assert 'overlap' in toolbar._button_map
            with patch.object(ui.Window,'show',show_without_workspace), patch.object(atk_loader,'_watch_launch',nullcontext):
                toolbar._button_map['overlap'].click()
            assert ui._window is window
            # Reload Scripts purges the whole isolated package, then relaunches.
            purged,_=atk_loader.reload_tool_modules()
            assert 'atk_overlap' in purged
            import atk_overlap.ui as fresh_ui
            with patch.object(fresh_ui.Window,'show',show_without_workspace), patch.object(atk_loader,'_watch_launch',nullcontext):
                atk_loader.launch_tool('overlap')
            assert fresh_ui._window is not window
            assert fresh_ui._window.objectName()=='ATKOverlapWindow' and fresh_ui._window.isVisible()
            fresh_ui._window.close()
            toolbar.close()
            cmds.optionVar(remove='atk_hidden_overlap') if cmds.optionVar(exists='atk_hidden_overlap') else None
    print('PASS: MEL install, package/assets/licence, registry, visibility, launcher, preview, direct bake/undo, legacy layer delete, icon, button, and reload')


try:
    main()
finally:
    maya.standalone.uninitialize()
