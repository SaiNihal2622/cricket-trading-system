"""Check current config endpoints."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import MIMO_BASE_URL, MIMO_MODEL, NVIDIA_BASE_URL, NVIDIA_MODEL, NVIDIA_FALLBACK_MODELS, GEMINI_MODEL
print(f"MiMo URL: {MIMO_BASE_URL}")
print(f"MiMo Model: {MIMO_MODEL}")
print(f"NVIDIA URL: {NVIDIA_BASE_URL}")
print(f"NVIDIA Model: {NVIDIA_MODEL}")
print(f"NVIDIA Fallbacks: {NVIDIA_FALLBACK_MODELS}")
print(f"Gemini Model: {GEMINI_MODEL}")