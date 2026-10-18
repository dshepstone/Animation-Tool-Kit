"""Discover and undoably remove only Overlap bake layers."""


def list_bakes():
    from maya import cmds
    return [n for n in cmds.ls(type='animLayer') or []
            if n.startswith(('Kinequill_overlap', 'Overlap_overlap')) or (
                cmds.attributeQuery('overlapBake', node=n, exists=True) and
                cmds.getAttr(n + '.overlapBake'))]


def delete_bake(layer):
    from maya import cmds
    from .maya_engine import scene_state
    if not layer or layer not in list_bakes() or layer == cmds.animLayer(query=True, root=True):
        raise ValueError('Choose an Overlap bake layer to delete')
    with scene_state('Overlap delete bake'):
        cmds.delete(layer)
