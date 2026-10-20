"""Enable the fixed management plugins without changing persisted credentials/config."""


def install_plugin_selection(app_class):
    original_load=app_class.load_plugins
    original_save=app_class._save_configurations

    async def load(self,plugins):
        self._ccdc_original_plugins=list(self.get_config('plugins') or [])
        self.set_config('main','plugins',['magma','ccdc'])
        return await original_load(self,['magma','ccdc'])

    async def save(self,*args,**kwargs):
        active=list(self.get_config('plugins') or [])
        self.set_config('main','plugins',getattr(self,'_ccdc_original_plugins',active))
        try:return await original_save(self,*args,**kwargs)
        finally:self.set_config('main','plugins',active)

    app_class.load_plugins=load
    app_class._save_configurations=save
