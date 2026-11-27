import types
from tests.test_remote_script_bridge import _load_script_module, make_instance, start_request, finish_request

class Item:
    def __init__(self, name, children=()): self.name=name; self.children=children; self.uri='uri:'+name; self.is_loadable=False


def test_search_yields_to_mutating_commands_and_reports_bounds():
    rs=_load_script_module();inst=make_instance(rs)
    inst.application=lambda:types.SimpleNamespace(browser=types.SimpleNamespace(instruments=Item('Root',[Item('Preset'+str(i)) for i in range(500)])))
    search,replies=start_request(inst,{'type':'search_browser','params':{'query':'Preset','category':'instruments','max_results':100,'max_nodes':70}})
    inst.update_display()
    assert inst._active_deferred is None and inst._background_deferred
    calls=[];inst._stop_playback=lambda:calls.append('stop')
    other,other_replies=start_request(inst,{'type':'stop_playback'})
    inst.update_display()
    finish_request(other,other_replies)
    assert calls==['stop'] and not replies
    for _ in range(8): inst.update_display()
    result=finish_request(search,replies)['result']
    assert result['visited']==70 and result['truncated'] and result['reason']=='node_limit'


def test_depth_time_and_missing_categories(monkeypatch):
    rs=_load_script_module();inst=make_instance(rs)
    root=Item('Root',[Item('Nested',[Item('Deep')])])
    inst.application=lambda:types.SimpleNamespace(browser=types.SimpleNamespace(instruments=root))
    op=inst._cmd_search_browser({'query':'Deep','max_depth':1})
    result=op.poll()
    assert result['truncated'] and result['reason']=='depth_limit'
    assert 'plugins' in result['unavailable_categories']
    monkeypatch.setattr(rs,'_command_clock',lambda:1.)
    op=inst._cmd_search_browser({'query':'Deep','max_ms':10})
    monkeypatch.setattr(rs,'_command_clock',lambda:2.)
    assert op.poll()['reason']=='time_limit'
