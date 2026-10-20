import ast
import asyncio
import contextlib
import importlib.util
import io
import pathlib
import os
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'payload/caldera'));CALDERA=pathlib.Path(os.environ.get('CALDERA_ROOT','/opt/summit-caldera'));sys.path.append(str(CALDERA))


class LauncherTests(unittest.TestCase):
    def test_launcher_arguments_match_actual_caldera_parser(self):
        if not (CALDERA/'server.py').is_file():self.skipTest('Set CALDERA_ROOT to the matching upstream checkout for parser acceptance')
        tree=ast.parse((ROOT/'payload/caldera/launch.py').read_text(encoding='utf-8-sig'))
        argv=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='argv' for t in node.targets))
        spec=importlib.util.spec_from_file_location('panel_deployed_server',str(CALDERA/'server.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        before=os.getcwd()
        try:
            os.chdir(CALDERA)
            with contextlib.redirect_stderr(io.StringIO()):
                try:args=module._get_parser().parse_args(argv[1:])
                except SystemExit:self.fail('Launcher plugin arguments rejected by deployed CALDERA parser')
        finally:os.chdir(before)
        self.assertEqual(args.plugins,['magma','ccdc'])

    def test_plugin_enablement_uses_runtime_config_without_touching_credentials(self):
        try:from plugins.ccdc.runtime import install_plugin_selection
        except ImportError:self.fail('Runtime plugin enablement missing')
        config={'plugins':['magma'],'users':{'red':{'organizer':'unchanged hash'}},'api_key_red':'unchanged key'}
        saved=[]
        class App:
            def set_config(self,name,prop,value):config[prop]=value
            def get_config(self,prop):return config[prop]
            async def load_plugins(self,plugins):return dict(requested=plugins,enabled=config['plugins'])
            async def _save_configurations(self,main_config_file='summit'):saved.append(dict(config))
        install_plugin_selection(App)
        app=App()
        self.assertEqual(asyncio.run(app.load_plugins(['magma','ccdc'])),dict(requested=['magma','ccdc'],enabled=['magma','ccdc']))
        self.assertEqual(config['users'],{'red':{'organizer':'unchanged hash'}})
        self.assertEqual(config['api_key_red'],'unchanged key')
        asyncio.run(app._save_configurations())
        self.assertEqual(saved[0]['plugins'],['magma'])
        self.assertEqual(config['plugins'],['magma','ccdc'])

if __name__=='__main__':unittest.main()
