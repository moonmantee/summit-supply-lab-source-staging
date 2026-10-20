from app.utility.base_world import BaseWorld
from .api import register_routes

name = 'CCDC Exercise'
description = 'Competition schedule editor and fixed-action exercise controls'
address = '/plugin/ccdc/gui'
access = BaseWorld.Access.RED


async def enable(services):
    register_routes(services)
