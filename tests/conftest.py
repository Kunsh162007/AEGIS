"""Force the offline mock provider for the whole test suite, regardless of any
real keys in .env — tests must be deterministic, free, and runnable anywhere.
Set before src.config is imported (it reads the environment at import time).
"""
import os

os.environ["MODEL_PROVIDER"] = "mock"
