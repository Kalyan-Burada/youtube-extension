# Force the HuggingFace `transformers` stack to use the PyTorch backend only.
# Without this, importing sentence-transformers pulls in transformers'
# TensorFlow integration, which hard-crashes on environments that have
# Keras 3 installed ("Keras 3 ... not yet supported in Transformers").
# These MUST be set before transformers is imported anywhere, so they live
# in the package __init__ which runs before any submodule.
import os

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
