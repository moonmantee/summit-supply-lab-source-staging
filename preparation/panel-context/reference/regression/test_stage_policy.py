import asyncio
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PolicyTests(unittest.TestCase):
    def test_legacy_task_api_serializes_links(self):
        from types import SimpleNamespace
        mod = self.load_policy()
        class Rest:
            async def task_agent_with_ability(self, **kwargs):
                return [SimpleNamespace(display={'id':'known-link'})]
        mod.install_task_serialization(Rest)
        self.assertEqual(asyncio.run(Rest().task_agent_with_ability(paw='pilot')), [{'id':'known-link'}])

    def load_policy(self):
        path = ROOT / 'stage_policy.py'
        self.assertTrue(path.is_file(), 'The management-only policy must exist')
        spec = importlib.util.spec_from_file_location('stage_policy', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_only_http_and_internal_events_are_registered(self):
        mod = self.load_policy()
        contacts = []
        class ContactService:
            async def register_contact(self, contact):
                contacts.append(contact)
        class App:
            def get_service(self, name):
                self.assert_name = name
                return ContactService()
            def get_services(self):
                return {'expected': True}
        def factory(services):
            self.assertEqual(services, {'expected': True})
            return 'http'
        mod.install_policy(App, object, factory, lambda services: 'internal-events')
        app = App()
        asyncio.run(app.register_contacts())
        self.assertEqual(contacts, ['http', 'internal-events'])
        self.assertEqual(app.assert_name, 'contact_svc')

    def test_restart_rejects_agent_operation_or_schedule_state(self):
        mod = self.load_policy()
        for collection in ('agents', 'operations', 'schedules'):
            with self.subTest(collection=collection):
                class Data:
                    async def restore_state(self):
                        self.ram = {collection: [object()]}
                mod.install_policy(type('App', (), {}), Data, None, None)
                with self.assertRaisesRegex(RuntimeError, 'management-only'):
                    asyncio.run(Data().restore_state())

    def test_empty_inventory_can_restore(self):
        mod = self.load_policy()
        class Data:
            async def restore_state(self):
                self.ram = {'agents': [], 'operations': [], 'schedules': [], 'abilities': [1]}
        mod.install_policy(type('App', (), {}), Data, None, None)
        data = Data()
        asyncio.run(data.restore_state())
        self.assertEqual(data.ram['abilities'], [1])

    def test_pilot_restore_clears_pending_work_and_rejects_other_identities(self):
        from types import SimpleNamespace
        mod = self.load_policy()
        for host in ('shop01', 'unexpected'):
            class Data:
                async def restore_state(self):
                    self.ram = {'agents': [SimpleNamespace(paw='summit-shop01', host=host,
                        group='summit-pilot', executors={'summit-pilot': object()}, links=[object()])]}
            mod.install_policy(type('App', (), {}), Data, None, None, pilot_hosts={'summit-shop01': 'shop01'})
            data = Data()
            if host == 'shop01':
                asyncio.run(data.restore_state())
                self.assertEqual(data.ram['agents'][0].links, [])
            else:
                with self.assertRaises(RuntimeError):
                    asyncio.run(data.restore_state())

    def test_schedulers_cannot_resume_or_dispatch(self):
        mod = self.load_policy()
        class App:
            def get_service(self, name):
                raise AssertionError('Disarmed policy must not access scheduler state')
        mod.install_policy(App, type('Data', (), {'restore_state': lambda self: None}), None, None)
        asyncio.run(App().resume_operations())
        asyncio.run(App().run_scheduler())


if __name__ == '__main__':
    unittest.main()
