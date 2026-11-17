import os
import tempfile

# Must run before the app is imported so settings pick up the test database
_tmp = tempfile.mkdtemp()
os.environ["CL_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CL_STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["CL_LLM_PROVIDER"] = "mock"
