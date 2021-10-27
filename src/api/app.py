log = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
from core import config
from core.server import Server
from feature.index.controller import IndexController
from feature.health import HealthController
import logging
from core.store.es_vec import ES
from queue_controller import Queue
import os
import operators

# this is not needed for docker local dev but for non docker local dev. might need to document how to do this
# for non docker local development.
# load_dotenv()
try:
    config = config.load("config.yml")

    current_operators = operators.intialize(config.operators)

    es_store = ES(config.store)
    es_store.connect()
    es_store.optionally_create_index()

    queue = Queue(config.queue)
    queue.connect()
    queue.declare_queues()

    health_controller = HealthController()
    index_controller = IndexController(
        store=es_store, operators=current_operators, queue=queue
    )

    server = Server(config.server, controllers=[health_controller, index_controller])
    server.start()
except Exception as e:
    log.exception("Error Initializing App")
