"""Load the shared, root-owned local transport; never load a supplied path."""
import importlib.util


class Client:
    def __init__(self):
        spec = importlib.util.spec_from_file_location('ccdc_admin_transport', '/opt/summit-caldera-fixtures/panel_client.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.client = module.AdminClient()

    def call(self, request, actor): return self.client.call(request, actor)
