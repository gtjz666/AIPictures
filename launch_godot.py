"""Godot's launcher can start from any editor working directory."""
import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
from aipictures.app import main

if __name__=='__main__':main()
