"""Management/benign pilot policy. Operations and schedules never resume."""


def install_ability_storage(manager_class):
    # The source/data symlink intentionally separates writable state from code.
    # Use the file service's directory+basename mode so its containment check
    # applies to the actual ability directory, without weakening that check.
    async def save_ability(self, file_path, data, obj_type, access):
        from pathlib import Path
        import yaml
        base = (Path.cwd() / 'data' / 'abilities').resolve()
        lexical = Path(file_path)
        path = lexical.resolve()
        if (lexical.is_absolute() or '..' in lexical.parts or not path.is_relative_to(base)
                or path.suffix != '.yml' or len(path.relative_to(base).parts) != 2):
            raise ValueError('Unexpected ability storage path')
        await self._file_svc.save_file(path.name, yaml.dump([data], encoding='utf-8', sort_keys=False),
                                       str(path.parent), encrypt=False)
        await self._data_svc.remove('abilities', dict(ability_id=data['id']))
        await self._data_svc.load_ability_file(str(path), access)
    manager_class._save_and_reload_object = save_ability


def install_task_serialization(rest_class):
    original = rest_class.task_agent_with_ability
    async def serialized_task(self, *args, **kwargs):
        return [link.display for link in await original(self, *args, **kwargs)]
    rest_class.task_agent_with_ability = serialized_task


def install_policy(app_class, data_class, http_factory, event_factory, pilot_hosts=None):
    pilot_hosts = dict(pilot_hosts or {})
    async def http_only(self):
        await self.get_service('contact_svc').register_contact(http_factory(self.get_services()))
        await self.get_service('contact_svc').register_contact(event_factory(self.get_services()))

    async def disarmed(self):
        return None

    original_restore = getattr(data_class, 'restore_state', None)
    if original_restore:
        async def restore_empty_inventory(self):
            await original_restore(self)
            if any(self.ram.get(key) for key in ('operations', 'schedules')):
                raise RuntimeError('Stage B is management-only; operational state requires the enrollment policy')
            for agent in self.ram.get('agents', []):
                if (not pilot_hosts or pilot_hosts.get(agent.paw) != agent.host or agent.group != 'summit-pilot'
                        or set(agent.executors) != {'summit-pilot'}):
                    raise RuntimeError('Stage B is management-only; unrecognized pilot state')
                # Single-agent benign work is never replayed after restart.
                agent.links = []
        data_class.restore_state = restore_empty_inventory

    app_class.register_contacts = http_only
    app_class.resume_operations = disarmed
    app_class.run_scheduler = disarmed
