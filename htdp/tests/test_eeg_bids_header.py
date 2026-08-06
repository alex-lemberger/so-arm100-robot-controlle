from htdp.export.eeg_bids import vhdr_text, vmrk_text


def test_vhdr_core_fields():
    text = vhdr_text("sub-p0001_task-t_acq-eeg", ["Fp1", "Fp2", "Cz"], 250.0)
    assert "BinaryFormat=IEEE_FLOAT_32" in text
    assert "DataFormat=BINARY" in text
    assert "DataOrientation=MULTIPLEXED" in text
    assert "NumberOfChannels=3" in text
    assert "SamplingInterval=4000.0" in text
    assert "DataFile=sub-p0001_task-t_acq-eeg_eeg.eeg" in text
    assert "MarkerFile=sub-p0001_task-t_acq-eeg_eeg.vmrk" in text


def test_vhdr_channel_lines():
    text = vhdr_text("stem", ["Fp1", "Cz"], 250.0)
    assert "Ch1=Fp1,,1,µV" in text
    assert "Ch2=Cz,,1,µV" in text


def test_vmrk_has_new_segment_and_datafile():
    text = vmrk_text("sub-p0001_task-t_acq-eeg")
    assert "Mk1=New Segment" in text
    assert "DataFile=sub-p0001_task-t_acq-eeg_eeg.eeg" in text
