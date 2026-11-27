import types
import pytest
np=pytest.importorskip('numpy')
sf=pytest.importorskip('soundfile')
pytest.importorskip('scipy')
from MCP_Server.ears import audio, analyze


def test_file_metadata_limits_precede_decoding(tmp_path,monkeypatch):
    path=tmp_path/'large.wav';path.write_bytes(b'header')
    monkeypatch.setattr(audio.sf,'info',lambda p:types.SimpleNamespace(samplerate=48000,channels=2,frames=100000000))
    monkeypatch.setattr(audio.sf,'read',lambda *a,**k:pytest.fail('must not allocate'))
    with pytest.raises(ValueError,match='limits'):audio.load_audio(path)


@pytest.mark.parametrize('kwargs',[{'bpm':float('nan')},{'beat_offset_s':float('inf')},{'start_s':float('nan')}])
def test_invalid_analysis_arguments_fail_before_dsp(kwargs):
    with pytest.raises(ValueError):analyze(np.zeros(480),sr=48000,**kwargs)


def test_nonfinite_file_samples_rejected(tmp_path):
    path=tmp_path/'nonfinite.wav';sf.write(path,np.array([0.,float('nan')]),48000,subtype='FLOAT')
    with pytest.raises(ValueError,match='nonfinite'):audio.load_audio(path)


def test_oversize_array_rejected_before_conversion():
    value=np.lib.stride_tricks.as_strided(np.zeros(1),shape=(audio.MAX_SAMPLES+1,),strides=(0,))
    with pytest.raises(ValueError,match='sample'):audio.as_frames(value,48000)
