"""Scene create/delete/duplicate, trigger, rename."""

from __future__ import absolute_import, print_function, unicode_literals


def create_scene(song, index, name, ctrl=None):
    """Create a new scene."""
    try:
        if index < 0:
            index = len(song.scenes)
        song.create_scene(index)
        scene = song.scenes[index]
        if name:
            scene.name = name
        return {"index": index, "name": scene.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error creating scene: " + str(e))
        raise


def delete_scene(song, scene_index, ctrl=None):
    """Delete a scene."""
    try:
        if scene_index < 0 or scene_index >= len(song.scenes):
            raise IndexError("Scene index out of range")
        song.delete_scene(scene_index)
        return {"deleted": True, "scene_index": scene_index}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error deleting scene: " + str(e))
        raise


def duplicate_scene(song, scene_index, ctrl=None):
    """Duplicate a scene."""
    try:
        if scene_index < 0 or scene_index >= len(song.scenes):
            raise IndexError("Scene index out of range")
        song.duplicate_scene(scene_index)
        new_index = scene_index + 1
        return {"new_index": new_index, "name": song.scenes[new_index].name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error duplicating scene: " + str(e))
        raise


def trigger_scene(song, scene_index, ctrl=None):
    """Trigger a scene."""
    try:
        if scene_index < 0 or scene_index >= len(song.scenes):
            raise IndexError("Scene index out of range")
        song.scenes[scene_index].fire()
        return {"triggered": True, "scene_index": scene_index}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error triggering scene: " + str(e))
        raise


def set_scene_name(song, scene_index, name, ctrl=None):
    """Set a scene's name."""
    try:
        if scene_index < 0 or scene_index >= len(song.scenes):
            raise IndexError("Scene index out of range")
        song.scenes[scene_index].name = name
        return {"scene_index": scene_index, "name": name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting scene name: " + str(e))
        raise
