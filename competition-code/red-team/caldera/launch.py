"""Pinned CALDERA launcher with the initial management-only competition policy."""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.contacts.contact_http import Contact
from app.contacts.contact_websocket import Contact as EventContact
from app.service.app_svc import AppService
from app.service.data_svc import DataService
from app.service.rest_svc import RestService
from app.api.v2.managers.ability_api_manager import AbilityApiManager
from stage_policy import install_policy, install_task_serialization, install_ability_storage
from plugins.ccdc.runtime import install_plugin_selection

install_ability_storage(AbilityApiManager)
install_task_serialization(RestService)
install_plugin_selection(AppService)
install_policy(AppService, DataService, Contact, EventContact, pilot_hosts={'summit-shop01': 'shop01','summit-sql01':'sql01','summit-dc01':'dc01','summit-forum01':'forum01','summit-mail01':'mail01','summit-workstation01':'workstation01.corp.summit.test'})
sys.argv = ['server.py', '-E', 'summit', '--log', 'INFO', '-P', 'magma,ccdc']
runpy.run_path(str(ROOT / 'server.py'), run_name='__main__')


