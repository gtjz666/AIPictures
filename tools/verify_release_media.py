"""Native Qt playback, seeking and exact export of already generated audio."""
import argparse
import json
import tempfile
import shutil
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from tools.verify_dock_workspace import wait_until


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audio',type=Path,nargs='+',required=True);parser.add_argument('--proof',type=Path,required=True);args=parser.parse_args()
    args.proof.mkdir(parents=True,exist_ok=False);app=create_application([])
    with tempfile.TemporaryDirectory() as temp,ExitStack() as cleanup,patch('aipictures.app.DATA',Path(temp)/'data'), \
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();cleanup.callback(lambda:(w.close(),QTest.qWait(60)));w.timer.stop();w.resize(1440,940);w.show();QTest.qWait(30)
        w.workbench.select_category('audio');a=w.audio_controller;a.output.setVolume(0);records=[]
        for i,path in enumerate(args.audio):
            value=json.loads(path.read_text('utf-8'));a.load(path);a.toggle();wait_until(lambda:a.player.position()>150,seconds=15)
            a.toggle();a.player.setPosition(1000);QTest.qWait(50)
            assert a.player.error()==a.player.Error.NoError,a.player.errorString()
            target=Path(temp)/f'export-{i}.wav'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):a.save()
            assert target.read_bytes()==Path(value['audio']).read_bytes()
            a.prompt.setPlainText(value['params'].get('source_brief',value['params']['prompt']))
            w.grab().save(str(args.proof/f'audio-{i}.png'))
            records.append(dict(source=str(path.resolve()),duration=value['duration_seconds'],seek_position=a.player.position(),export_exact=True,decoder_ok=True))
            a.stop();assert a.player.source().isEmpty()
        # A real loaded WAV must also be deletable through the audio history UI.
        cached=a.data/'audio'/'playback-deletion-check';cached.mkdir(parents=True)
        copy=dict(value,audio=str(cached/'audio.wav'));shutil.copyfile(value['audio'],cached/'audio.wav');write_json(cached/'audio.json',copy)
        a.load(cached/'audio.json');a.toggle();wait_until(lambda:a.player.position()>120,seconds=15)
        a.load_history();a.history.item(0).setSelected(True);w.clear_result_cache('audio');wait_until(lambda:not w.cache_busy)
        assert not cached.exists() and a.manifest is None
        write_json(args.proof/'acceptance.json',dict(native_qt=True,muted_playback=True,records=records,no_new_inference=True,loaded_audio_cache_deletion=True))
    print('Real audio playback / seek / exact export / release: PASS')


if __name__=='__main__':main()
